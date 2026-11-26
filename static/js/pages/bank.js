"use strict";
/* ---------------- Bank and reconciliation ---------------- */
// The year view of one account (a row per month), a month's panel opened in place, the review of a statement's lines and
// the print preview of the reconciliation statement (Bank.dc.html, BankReview.dc.html, PrintBankRec.dc.html). What matches,
// what is in the books, whether a month can be signed off and what is locked is worked out by the server (hrp/recon.py);
// nothing here posts anything to SQL Account. A signed-off month is locked: its lines, matches and book opening can't
// change until it is reopened, with a reason.
const RC_PILL = { to_import: "grey", to_review: "warn", difference: "bad", reconciled: "ok" };
const rcPill = (status, text) => `<span class="pill ${RC_PILL[status] || "grey"}">${esc(text)}</span>`;
const rcUrl = (what, extra = "") => `/api/recon/${what}?entity_id=${state.entity}${extra}`;
const signedAmt = (n, cur) => `${n < 0 ? "−" : "+"}${money(Math.abs(n), cur).replace(/^\S+ /, "")}`;
const dayCount = n => `${n} day${n === 1 ? "" : "s"}`;
const plural1 = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
const bankText = (l, cur) => [fmtDate(l.txn_date), l.txn_date, l.description, LT.amount(l.amount), cur, l.payment_desc, l.note,
  (l.group || []).map(p => p.description).join(" "), l.status === "no_docs" ? "no documents needed" : l.payment_id ? "" : "not explained"].join(" ");
const lockedPill = () => `<span class="pill grey bk-lock">${icon("lock")}Locked</span>`;
// The name typed under Prepared by is kept on this computer only (declared, not verified), so it is filled in next time.
const PREP_KEY = "hrp-prepared-by";
const preparedBy = () => { try { return localStorage.getItem(PREP_KEY) || ""; } catch { return ""; } };
const keepPreparedBy = v => { try { if (v) localStorage.setItem(PREP_KEY, v); } catch { /* private window: not kept */ } };
const reconXlsx = s => `/api/export/recon.xlsx?entity_id=${state.entity}&account_id=${s.account.id}&month=${s.month}`;
// The reading back after a change made on this page (core/saved.js): the review that is open, else the year; once another page (or another
// company's or month's) is on show, that page. Ask for it before the change is sent. reset: as for reloadReview.
const bankAgain = (reset = true) => savedPagePart(pageHere(), () => state.recon.rv ? reloadReview(reset) : drawRecon());

// SQL entries the lock kept from being linked (Link or create all, an import): how many and why, for the SQL page's
// toast and result ("2 entries were not linked: Main September 2026 is marked reconciled and locked").
function heldNote(held) {
  if (!held?.length) return "";
  const why = String(held[0].why || "").split(", so ")[0];
  return `. ${held.length} ${held.length === 1 ? "entry was" : "entries were"} not linked: ${why}`;
}

// The books' side of a month as one cell: the balance, or why there is none.
const bookCell = (b, cur) => b.closing != null ? money(b.closing, cur) : `<span class="muted">${esc(b.note || "—")}</span>`;

// Sign-off controls for a month (s: the month's summary), the same in its panel and at the foot of its review.
function signBlock(s) {
  if (!s.statement) return "";
  const id = s.statement.id, e = ent(), last = s.reopens?.[0];
  if (s.locked) {
    const at = fmtDate(s.locked_at), before = s.locked_how === "before tracking";
    const note = s.sign_note?.length ? `<div class="bk-note"><b>Sign-off note, as kept ${esc(at)}</b>
        <ul>${s.sign_note.map(t => `<li>${esc(t)}</li>`).join("")}</ul>${s.free_note && !before ? `<div>Note: ${esc(s.free_note)}</div>` : ""}
        <div class="note">Written by the app at sign-off, as the month stood. It is printed on the reconciliation statement and in the audit pack; reopening the month keeps it in the audit trail.</div></div>` : "";
    const task = s.recon_task;
    const filed = task ? `<div class="bk-filed"><span>${task.documents.length ? `Signed statement filed on ${esc(task.title)}: ${task.documents.map(d => `<a href="/api/documents/${d.id}/file" target="_blank" rel="noopener">${esc(d.original_name)}</a>`).join(", ")}`
        : `Print the reconciliation statement, have it signed, and file the signed copy on the month's ${esc(task.title)} checklist item.`}</span>
        <button type="button" class="ghost small" data-rc-signed="${task.id}" data-code="${esc(s.statement_code)}">${icon("upload")}Upload the signed statement</button></div>` : "";
    return `<div class="bk-sign" id="bk-sign-${id}"><div class="rc-sign"><span class="pill ok">${icon("check")}Reconciled ${esc(at)}${before ? " · before tracking" : ""}</span>${lockedPill()}
        ${s.free_note && before ? `<span class="note">${esc(s.free_note)}</span>` : ""}${s.prepared_by ? `<span class="note">Prepared by ${esc(s.prepared_by)} (declared)</span>` : ""}
        <button type="button" class="ghost small" id="bk-reopen-${id}" data-rc-reopen="${id}">Reopen month</button></div>
      <div class="note">Locked since ${esc(at)}: its lines, matches and book opening can't change${e.uses_sql ? "" : ", and nothing can be posted into it"}. Reopen the month to change anything.</div>
      ${last ? `<div class="note muted">Reopened ${esc(fmtDate(last.at))} (${esc(last.reason)}), then marked reconciled again.</div>` : ""}
      ${note}${filed}</div>${rcChanged(s)}`;
  }
  const why = s.why_not.length ? `<div class="note" id="bk-why-${id}">Not ready: ${esc(s.why_not.join("; "))}.</div>` : "";
  const reopened = last ? `<div class="banner info bk-reopened">${icon("history")}<div><b>Reopened ${esc(fmtDate(last.at))}</b>
      <span>Reason: ${esc(last.reason)}. Mark it reconciled again once the month is reviewed.</span></div></div>` : "";
  const before = s.before_tracking ? `<div class="rc-before"><div class="note">This month is before tracking began here. If it was reconciled outside this app, say so.</div>
      <label class="field"><span>How it was reconciled${s.book_matches ? " (optional: the books agree with the bank)" : ""}</span><input data-rc-note="${id}" maxlength="200" placeholder="e.g. reconciled in SQL Account in August"></label>
      <label class="row"><input type="checkbox" data-rc-before-tick="${id}"> This month was reconciled before tracking began</label>
      <button class="ghost" data-rc-before="${id}" ${s.can_sign_before_tracking ? "" : "disabled"}>Reconciled before tracking</button>
      ${s.can_sign_before_tracking ? "" : `<div class="note">The statement has to add up first.</div>`}</div>` : "";
  return `${reopened}<div class="bk-sign" id="bk-sign-${id}">
      <div class="bk-signform">
        <label class="field"><span>Note for the sign-off <span class="muted">Optional</span></span><textarea data-rc-free="${id}" maxlength="500" rows="2"></textarea></label>
        <label class="field"><span>Prepared by <span class="muted">Your name, as declared on this computer</span></span><input data-rc-by="${id}" maxlength="80" value="${esc(preparedBy())}" autocomplete="name"></label>
      </div>
      <div class="note">The app writes the rest of the note itself at sign-off: each confirmed pair with its reason, each line explained without documents, and anything left as a reconciling item.</div>
      <div class="rc-sign"><button class="btn" id="bk-mark-${id}" data-rc-sign="${id}" ${s.can_sign ? "" : "disabled"} ${why ? `aria-describedby="bk-why-${id}"` : ""}>Mark reconciled</button>${why}</div></div>${before}`;
}

// A month signed off before SQL's receipts and payments counted by their lines on the bank, whose book figures that
// changed: the figures then and now, and the owner's confirmation asked for (the sign-off stays until then).
function rcChanged(s) {
  const ch = s.book_changed;
  if (!ch || !s.statement) return "";
  const cur = s.account.currency, row = (k, w) => `<tr><td>${w}</td><td class="num">${money(ch.old[k], cur)}</td><td class="num">${money(ch.new[k], cur)}</td></tr>`;
  return `<div class="banner warn rc-changed"><b>${esc(ch.text)}</b>
    <span>SQL's receipts and payments now count by what each one posted to the bank account, not by its listing amount.</span>
    <div class="tbl-wrap"><table><caption class="sr-only">Book figures at sign-off and now</caption><thead><tr><th>Figure</th><th class="num">At sign-off</th><th class="num">Now</th></tr></thead><tbody>
      ${row("in", "Money in")}${row("out", "Money out")}${row("closing", "Book closing")}</tbody></table></div>
    <div class="row"><button class="btn small" data-rc-reconfirm="${s.statement.id}" ${s.can_reconfirm ? "" : "disabled"}>Confirm again</button>
      ${s.reconfirm_why ? `<span class="note">${esc(s.reconfirm_why)}</span>` : ""}</div></div>`;
}

// The month-end check of the cash book against SQL's own bank account (s.sql_check), in words.
function rcSqlCheck(s) {
  const k = s.sql_check;
  if (!k) return "";
  return `<div class="note rc-sqlcheck">${k.state === "agrees" ? `<span class="pill ok">${esc(k.text)}</span>` : k.state === "differs" ? `<span class="pill bad">Check against SQL</span> ${esc(k.text)}` : esc(k.text)}</div>`;
}

// Kept in SQL Account: a bank charge or bank profit explained here still has to be entered in SQL, or the books never agree
// with the bank. Not for a month before tracking began, or one marked reconciled before tracking: SQL has those already.
const sqlTodo = s => s.uses_sql && s.source === "sql" && !s.before_tracking && s.locked_how !== "before tracking";
const sqlWhy = (s, why) => why + (sqlTodo(s) && /^No payment needed/.test(why) ? " · Enter this in SQL Account" : "");

function rcTable(title, rows, cur, s) {
  if (!rows.length) return "";
  return `<div class="tbl-wrap"><h3>${esc(title)} · ${rows.length}</h3><table><thead><tr><th>Date</th><th>Description</th><th class="num">Amount</th><th>Why</th></tr></thead><tbody>
    ${rows.map(x => `<tr><td class="mono">${shortDate(x.date)}</td><td class="line-desc">${x.ref ? `<b>${esc(x.ref)}</b> ` : ""}${esc((x.description || "").replaceAll(" | ", " · "))}</td>
      <td class="num">${signedAmt(x.amount, cur)}</td><td class="note">${esc(s ? sqlWhy(s, x.why) : x.why)}</td></tr>`).join("")}</tbody></table></div>`;
}

function monthPanel(s) {
  const cur = s.account.currency, st = s.statement, rc = s.reconciliation, c = s.lines;
  if (!st) return `<div class="rc-panel"><div class="note">The ${esc(s.label)} statement for ${esc(s.account.label)} isn't imported yet. Import it above.</div>
    <div class="stats"><div class="stat"><b>${bookCell(s.book, cur)}</b><span>Book closing</span></div></div></div>`;
  const diff = s.difference;
  const parts = !rc ? [] : [
    rc.brought_forward ? `${money(rc.brought_forward, cur)} brought forward from last month (bank opening less book opening)` : "",
    rc.books_out ? `${money(rc.books_out, cur)} paid out in the books, not on the statement` : "",
    rc.books_in ? `${money(-rc.books_in, cur)} received in the books, not on the statement` : "",
    rc.bank_net ? `${money(rc.bank_net, cur)} net on the statement, not in the books` : "",
    rc.differ ? `${money(rc.differ, cur)} from matched amounts that differ` : "",
    rc.other ? `${money(rc.other, cur)} not explained by any of these` : ""].filter(Boolean);
  const gone = s.left_out.journals || s.left_out.invoices, unk = s.left_out.unknown, other = s.left_out.other_bank || 0;
  const pairsLeft = (s.pairs || []).filter(p => !p.confirmed_at).length;
  return `<div class="rc-panel">
    ${rcSqlCheck(s)}
    <div class="stats">
      <div class="stat"><b>${money(st.money_in, cur)}</b><span>Money in</span></div>
      <div class="stat"><b>${money(st.money_out, cur)}</b><span>Money out</span></div>
      <div class="stat"><b>${money(st.closing, cur)}</b><span>Bank closing</span></div>
      <div class="stat"><b>${bookCell(s.book, cur)}</b><span>Book closing</span></div>
      <div class="stat"><b class="${diff == null ? "" : Math.abs(diff) < 0.005 ? "recv" : "bad-text"}">${diff == null ? "—" : money(diff, cur)}</b><span>Difference (bank less books)</span></div>
    </div>
    <div class="row spread"><div>Lines: <b>${c.matched}</b> matched · <b>${c.confirmed}</b> confirmed · <b>${c.to_explain}</b> to explain
      ${st.adds_up ? "" : `<span class="pill bad">Statement doesn't add up</span>`}${s.pairs?.length ? ` · No money moved: <b>${s.pairs.length}</b>${pairsLeft ? ` (${pairsLeft} to confirm)` : ""}` : ""}</div>
      <div class="row">${st.document_id ? `<a class="ghost small" href="/api/documents/${st.document_id}/file" target="_blank" rel="noopener" aria-label="Statement PDF, ${esc(s.label)}">Statement PDF</a>` : ""}
      <a class="ghost small" href="${reconXlsx(s)}" aria-label="Excel of ${esc(s.label)}">${icon("sheet")}Excel</a>
      <button class="btn small" data-rc-review="${st.id}" aria-label="Review lines, ${esc(s.label)}">Review lines</button></div></div>
    <div class="row spread"><h3>Reconciliation statement</h3>
      <button type="button" class="ghost small" data-rc-print="${s.month}" aria-label="Print the reconciliation statement, ${esc(s.account.label)}, ${esc(s.label)}">${icon("printer")}Print the reconciliation statement</button></div>
    ${s.book.state !== "ok" ? `<div class="note">${esc(s.book.note)}${s.book.note === "Needs book opening" ? ": type this account's book balance under Book opening below." : " on the SQL import page."}</div>` : ""}
    ${diff != null && Math.abs(diff) >= 0.005 ? `<div class="note">The books are ${money(Math.abs(diff), cur)} ${diff > 0 ? "below" : "above"} the bank.${parts.length ? " That is: " + esc(parts.join("; ")) + "." : ""}</div>` : ""}
    ${rcTable("In the books, not on this statement", s.books_only, cur)}${rcTable("On the statement, not in the books", s.bank_only, cur, s)}
    ${s.differ.length ? `<div class="tbl-wrap"><h3>Matched, but the amounts differ · ${s.differ.length}</h3><table><thead><tr><th>Payment</th><th class="num">Books</th><th class="num">Statement</th><th class="num">Difference</th></tr></thead><tbody>
      ${s.differ.map(x => `<tr><td>${x.ref ? `<b>${esc(x.ref)}</b> ` : ""}${esc(x.description)}</td><td class="num">${money(x.book, cur)}</td><td class="num">${money(x.bank, cur)}</td><td class="num">${money(x.amount, cur)}</td></tr>`).join("")}</tbody></table></div>` : ""}
    ${!s.books_only.length && !s.bank_only.length && !s.differ.length && s.book.state === "ok" ? `<div class="note">Everything on the statement is in the books, and the other way round.</div>` : ""}
    ${gone ? `<div class="note">Not counted as bank movements: ${s.left_out.journals} journal${s.left_out.journals === 1 ? "" : "s"} and ${s.left_out.invoices} customer invoice${s.left_out.invoices === 1 ? "" : "s"} (customer refunds included) in the SQL listing. Fetch SQL's GL Journal of Transaction to count a journal that moves the bank.</div>` : ""}
    ${unk ? `<div class="note">Not counted: ${unk} cash book entr${unk === 1 ? "y" : "ies"} with no money in or out shown, so the books may differ by that amount.</div>` : ""}
    ${other ? `<div class="note">Not counted: ${plural(other, "receipt or payment", "receipts or payments")} whose lines in SQL don't touch this bank account (paid from another account).</div>` : ""}
    ${s.listing_note ? `<div class="note">${esc(s.listing_note)}</div>` : ""}
    ${s.uses_sql ? `<div class="note">For the reconciliation, fetch only the bank's cash book listing: a voucher paid from petty cash or a card would count as a bank movement.</div>` : ""}
    ${signBlock(s)}
    <div class="note">${signFoot()}</div></div>`;
}
const signFoot = () => ent().uses_sql ? "Marking a month reconciled locks it here. Nothing is posted to SQL Account; a change in SQL after the sign-off asks you to confirm it again."
  : "Marking a month reconciled locks it in this company's books here: payments dated in it can't change until it is reopened.";

async function viewBank(main) {
  const e = ent(), R = state.recon;
  if (R.entity !== state.entity) Object.assign(R, { entity: state.entity, account: null, year: null, open: null, panel: null, rv: null, print: null });
  // A print preview is of the statement as it stood when Print was pressed: drawing the page again (coming back to it,
  // or a Next up link) shows the month as it stands, and Print makes a new one.
  R.print = null;
  // Opened from Before you print or Next up: that account is shown, and with lines to explain its review opens.
  const focus = state.focusBank;
  if (focus?.account && e.accounts.some(a => a.id === focus.account)) { if (R.account !== focus.account) { R.rv = null; R.print = null; } R.account = focus.account; }
  if (!e.accounts.some(a => a.id === R.account)) R.account = defaultAccount(e)?.id;
  if (focus && state.month) R.year = state.month.slice(0, 4);
  const acctOpts = pickAccounts(e, R.account).map(a => acctOption(a, R.account, true)).join("");
  main.innerHTML = `${entityPicker()}
    <div class="card"><h1>Bank and reconciliation</h1>
      <div class="note">Import each month's Maybank statement PDF. Every line is matched to a payment automatically where the payee and amount agree (split DuitNow transfers are added together). Then review the month: confirm what was matched, explain the rest, and sign it off once the books agree with the bank. A signed-off month is locked; reopening it needs a reason and the sign-off again.</div>
      <form class="row" id="stmtForm"><label class="field"><span>Account</span><select id="stmtAcct">${acctOpts}</select></label>
      <label class="field"><span>Statement PDF</span><input id="stmtFile" type="file" accept=".pdf"></label>
      <button class="btn" type="submit" style="align-self:end">Import statement</button>
      <button class="ghost" type="button" id="rematch" style="align-self:end">Match again</button></form></div>
    <div id="stmtList"></div>`;
  await drawRecon(focus);
}

// The year view, the review and the print preview share the page's #stmtList: one part (core/page.js), so the one asked for last is drawn.
function drawRecon(focus) { return pageDraw("bank", page => reconDraw(page, focus)); }
async function reconDraw(page, focus) {
  const R = state.recon, box = $("#stmtList");
  if (!box) return;
  const used = () => { if (focus && state.focusBank === focus) state.focusBank = null; };
  if (R.print) { used(); return drawPrint(); }
  if (R.rv) { used(); return reloadReview(false); }
  const e = ent();
  const y = await page.read(api(rcUrl("year", `&account_id=${R.account}${R.year ? `&year=${R.year}` : ""}`)));
  used();
  R.year = y.year; R.data = y;
  if (focus) {
    const row = y.rows.find(r => r.month === state.month && r.statement_id);
    if (row && state.bankOnly) return openReview(row.statement_id, false);  // the page is at the top already
    if (row) R.open = row.month;
  }
  R.panel = R.open && y.rows.some(r => r.month === R.open) ? await page.read(api(rcUrl("month", `&account_id=${R.account}&month=${R.open}`))) : null;
  const cur = y.account.currency;
  const rowHtml = r => `<tr class="${R.open === r.month ? "focus" : ""}"><td><button class="link" id="bk-m-${r.month}" data-rc-open="${r.month}" aria-expanded="${R.open === r.month}">${esc(r.label)}</button></td>
      <td><div class="bk-status">${rcPill(r.status, r.status_text)}${r.locked ? lockedPill() : ""}${r.reopened_at ? `<span class="muted small">Reopened ${esc(shortDate(r.reopened_at))}</span>` : ""}</div>${r.book_changed ? `<div class="note bad-text">${esc(r.book_changed.text)}: book closing ${money(r.book_changed.old.closing, cur)} at sign-off, ${money(r.book_changed.new.closing, cur)} now (in ${money(r.book_changed.old.in, cur)} → ${money(r.book_changed.new.in, cur)}, out ${money(r.book_changed.old.out, cur)} → ${money(r.book_changed.new.out, cur)})</div>` : ""}</td>
      <td class="num">${r.bank_closing != null ? money(r.bank_closing, cur) : "—"}</td><td class="num">${bookCell({ closing: r.book_closing, note: r.book_note }, cur)}</td>
      <td>${r.reconciled_at ? fmtDate(r.reconciled_at) + (r.reconciled_how === "before tracking" ? ` <span class="muted">· before tracking</span>` : "") : "—"}</td>
      <td class="noprint">${r.document_id ? `<a href="/api/documents/${r.document_id}/file" target="_blank" rel="noopener">PDF</a>` : "—"}</td></tr>
      ${R.open === r.month && R.panel ? `<tr class="panelrow"><td colspan="6">${monthPanel(R.panel)}</td></tr>` : ""}`;
  const openings = y.openings.map(o => `${monthName(o.month)}: ${money(o.amount, cur)}`).join(" · ");
  const firstMonth = y.openings[0]?.month || y.rows.filter(r => r.statement_id).map(r => r.month).sort()[0] || y.rows.map(r => r.month).sort()[0] || "";
  box.innerHTML = `<div class="card">
      <div class="row spread"><div><div class="row bk-co"><span class="eyebrow">${esc(e.name)}</span><span class="pill grey">${icon(e.uses_sql ? "database" : "books")}${esc(keptLabel(e))}</span></div><h2 id="bk-year-h">${esc(y.account.label)} · ${esc(y.year)}</h2></div>
      <div class="row noprint">${pickAccounts(e, R.account).length > 1 ? pickAccounts(e, R.account).map(a => `<button class="${a.id === R.account ? "btn" : "ghost"} small" data-rc-acct="${a.id}" aria-pressed="${a.id === R.account}">${esc(a.label)}</button>`).join("") : ""}
      ${y.years.length > 1 ? y.years.map(yr => `<button class="${yr === y.year ? "btn" : "ghost"} small" data-rc-year="${yr}" aria-pressed="${yr === y.year}">${esc(yr)}</button>`).join("") : ""}</div></div>
      <div class="note">Click a month for its summary. Book closing comes from ${esc(y.source)}.</div>
      ${y.listing_note ? `<div class="note">${esc(y.listing_note)}</div>` : ""}
      <div class="tbl-wrap"><table><caption class="sr-only">Months of ${esc(y.account.label)}, ${esc(y.year)}, newest first</caption><thead><tr><th>Month</th><th>Status</th><th class="num">Bank closing</th><th class="num">Book closing</th><th>Reconciled on</th><th class="noprint">Statement</th></tr></thead><tbody>
      ${y.rows.map(rowHtml).join("") || `<tr><td colspan="6" class="empty">No months to show for ${esc(y.year)}.</td></tr>`}</tbody></table></div></div>
    <div class="card noprint"><h2>Book opening</h2>
      <div class="note">The balance ${esc(y.account.label)} had in your books on the first day of its first month here${e.uses_sql ? " (your SQL Account bank balance)" : ""}. Type it once; each later month carries on from the month before. ${openings ? `Set so far: ${esc(openings)}.` : "None set yet, so book closing shows Needs book opening."}</div>
      <form class="row" id="openingForm"><label class="field"><span>Month it applies to</span><input id="openMonth" type="month" required value="${esc(firstMonth)}"></label>
      <label class="field"><span>Book balance (${esc(cur)})</span><input id="openAmount" inputmode="decimal" required placeholder="e.g. 25,367.58"></label>
      <button class="btn" type="submit" style="align-self:end">Save book opening</button></form></div>`;
}

/* ---- Reopen month: a reason is required; the reopening is logged and the month needs the sign-off again ---- */
function reopenDialog(sid) {
  const s = state.recon.rv?.d.summary.statement?.id === sid ? state.recon.rv.d.summary : state.recon.panel;
  if (!s || s.statement?.id !== sid) return;
  const at = fmtDate(s.locked_at), before = s.locked_how === "before tracking";
  state.drawerDirty = () => !!$("#bk-why")?.value.trim();
  $("#drawer").innerHTML = `<div class="bk-dlg"><div class="row spread"><h2>Reopen ${esc(s.label)} for ${esc(s.account.label)}?</h2>
      <button type="button" class="ghost small" id="closeDrawer" aria-label="Close">${icon("close")}</button></div>
    <p class="note" id="bk-dlg-d">It was marked reconciled on ${esc(at)}${before ? " (before tracking)" : ""} and is locked.</p>
    <p class="note">Reopening unlocks the month's lines and its book opening. The month goes back to To review and needs the sign-off again.</p>
    <label class="field"><span>Why are you reopening this month? <span class="muted">Required</span></span>
      <textarea id="bk-why" rows="3" maxlength="300" aria-describedby="bk-why-err bk-why-hint" aria-required="true"></textarea></label>
    <div class="note bad-text" id="bk-why-err" role="alert"></div>
    <div class="note" id="bk-why-hint">The reopen and its reason are kept in the audit trail.</div>
    <div class="row bk-dlg-actions"><button type="button" class="ghost" id="bk-dlg-cancel">Cancel</button>
      <button type="button" class="btn" id="bk-dlg-go" data-sid="${sid}">Reopen month</button></div></div>`;
  showDrawer("new");
  $("#bk-why")?.focus?.();
}

async function reopenGo(btn) {
  const sid = +btn.dataset.sid, why = $("#bk-why")?.value.trim() || "";
  const err = $("#bk-why-err");
  if (!why) { if (err) err.textContent = "Say why you're reopening this month."; $("#bk-why")?.setAttribute("aria-invalid", "true"); $("#bk-why")?.focus(); return; }
  btn.disabled = true; btn.textContent = "Reopening…"; btn.setAttribute("aria-busy", "true");
  const here = dialogHere(), s = rcShown(), again = bankAgain();   // the month as asked about: another may be on show by the time the server answers
  try {
    await api("/api/recon/reopen", { json: { entity_id: state.entity, statement_id: sid, reason: why } });
  } catch (e) {
    btn.disabled = false; btn.textContent = "Reopen month"; btn.removeAttribute("aria-busy");
    if (!here()) return toast(`${s?.label || "The month"}: ${changeError(e)}`, true);
    if (err) err.textContent = changeError(e);   // refused: nothing was changed (a later month carries on from this one)
    return;
  }
  if (here()) await closeDrawer(true);
  // No Undo: signing off again is its own step (Mark reconciled, or Reconciled before tracking), never a toast's.
  toast(`${s?.label || "The month"} reopened${s ? ` for ${s.account.label}` : ""}. It needs the sign-off again.`);
  return afterSaved(again);
}

// The month on screen: the review's, else the open panel's.
const rcShown = () => state.recon.rv ? state.recon.rv.d.summary : state.recon.panel;

// Mark reconciled, with the optional note and Prepared by. No Undo: a signed-off month is reopened with a reason a
// person gives (Reopen month), never by a toast.
async function rcSign(sid, note, by) {
  keepPreparedBy(by);
  const s = rcShown(), again = bankAgain();
  await api("/api/recon/sign-off", { json: { entity_id: state.entity, statement_id: sid, note, prepared_by: by } });
  toast(`Marked as reconciled. ${s?.label || "The month"} is locked for ${s?.account.label || "this account"}.`);
  return afterSaved(again);
}

// The signed statement, filed on the month's bank reconciliation checklist item under a name that starts with the
// statement's code, so each account's signed copy is told apart on the item the accounts share.
async function rcSignedUpload(taskId, code) {
  const files = await pickFile(false); if (!files.length) return;
  const f = files[0], fd = new FormData();
  fd.append("file", f, f.name.toUpperCase().startsWith(code.toUpperCase()) ? f.name : `${code} signed ${f.name}`);
  fd.append("task_id", taskId); fd.append("doc_type", "recon");
  await api("/api/upload", { form: fd });
  toast(`Filed the signed statement ${code}.`);
  return afterSaved(render);
}

/* ---- the print preview of the reconciliation statement (PrintBankRec) ---- */
function openPrint(month) { return pageDraw("bank", page => printOpen(page, month)); }
async function printOpen(page, month) {
  const R = state.recon, sid = rcShown()?.statement?.id;
  // the name typed under Prepared by, else the one remembered on this computer
  const by = (sid && document.querySelector(`[data-rc-by="${sid}"]`)?.value.trim()) || preparedBy();
  keepPreparedBy(by);
  const r = await page.read(api("/api/recon/print", { json: { entity_id: state.entity, account_id: R.account, month, printed_by: by } }));
  R.print = { month, ...r };
  drawPrint();
  $("#stmtList")?.scrollIntoView?.({ block: "start" });
}

function drawPrint() {
  const R = state.recon, box = $("#stmtList"), P = R.print;
  if (!box || !P) return;
  const d = P.preview, cur = d.currency;
  const amt = (v, kind) => v == null || ((kind === "item" || kind === "head") && Math.abs(v) < 0.005) ? "—" : kind === "item" || kind === "head" ? signedAmt(v, cur) : money(v, cur).replace(/^\S+ /, "");
  box.innerHTML = `<div class="card bk-print">
    <div class="row spread"><div><div class="eyebrow">${esc(d.account)}</div><h2 id="bk-print-h">Reconciliation statement · ${esc(d.month_label)}</h2></div>
      <div class="row noprint"><button class="ghost small" data-rc-print-back="1">← Back to the year</button>
        <a class="btn small" href="${esc(P.url)}" target="_blank" rel="noopener">${icon("external")}Open the PDF</a>
        <a class="ghost small" href="${esc(P.url)}&download=1">${icon("download")}Download</a></div></div>
    ${desktopNote("The reconciliation statement", "The printed statement is laid out for A4 paper; open it on a computer to check and print it.")}
    <div class="bk-sheet" role="document" aria-label="Printed bank reconciliation statement ${esc(d.code)} for ${esc(d.company)}, ${esc(d.account)}, ${esc(d.month_label)}">
      <div class="bk-sheet-head"><div><b class="bk-sheet-title">Bank reconciliation statement</b><div><b>${esc(d.company)}</b></div>
        ${d.reg ? `<div class="small">${esc(d.reg)}</div>` : ""}${d.address ? `<div class="small">${esc(d.address)}</div>` : ""}
        <div><b>${esc(d.account)}</b></div><div class="small">${esc(d.month_label)} · ${esc(cur)} · Printed ${esc(d.printed)}</div></div>
        <div class="bk-code"><span class="pill ${d.signed ? "ok" : "warn"}">${d.signed ? "Signed off · as it prints" : "Not signed off · as it prints"}</span>
          <b class="mono">${esc(d.code)}</b><span class="mono">Check: ${esc(d.check)}</span><span class="muted small">${icon("qr")}QR printed on the PDF</span></div></div>
      <div class="bk-signline ${d.signed ? "" : "open"}">${esc(d.sign_line)}</div>
      <h3>1 Reconciliation at ${esc(d.as_at)}</h3>
      <div class="tbl-wrap"><table><caption class="sr-only">The bank balance, the items between the bank and the books, and the book balance</caption>
        <thead><tr><th>Date</th><th>Reference</th><th>Item</th><th class="num">Each</th><th class="num">${esc(cur)}</th></tr></thead><tbody>
        ${d.rec.map(r => `<tr class="bk-${r.kind}"><td>${esc(r.date)}</td><td class="mono">${esc(r.ref)}</td><td>${esc(r.item)}${r.why ? ` <span class="muted">· ${esc(r.why)}</span>` : ""}</td>
          <td class="num">${r.kind === "item" ? amt(r.each, "item") : ""}</td><td class="num">${r.kind === "item" ? "" : amt(r.total, r.kind)}</td></tr>`).join("")}</tbody></table></div>
      <div class="note"><b>${esc(d.rec_line)}</b></div>${d.rec_notes.map(t => `<div class="note">${esc(t)}</div>`).join("")}
      <h3>2 Book entries where no money moved</h3>
      ${d.pairs.length ? `<div class="tbl-wrap"><table><thead><tr><th>Document</th><th>Date</th><th>Description</th><th class="num">Money in</th><th class="num">Money out</th></tr></thead><tbody>
        ${d.pairs.map(p => p.docs.map(x => `<tr><td class="mono">${esc(x.ref)}</td><td>${esc(x.date)}</td><td>${esc(x.description)}</td><td class="num">${x.in ? money(x.in, cur).replace(/^\S+ /, "") : ""}</td><td class="num">${x.out ? money(x.out, cur).replace(/^\S+ /, "") : ""}</td></tr>`).join("")
          + `<tr><td><b>${esc(p.net)}</b></td><td colspan="4"><i>Reason: ${esc(p.reason)}. ${esc(p.status)}.</i></td></tr>`).join("")}</tbody></table></div>` : ""}
      ${d.pair_notes.map(t => `<div class="note">${esc(t)}</div>`).join("")}
      <h3>3 Totals check</h3>
      ${d.totals.length ? `<div class="tbl-wrap"><table><thead><tr><th>${esc(cur)}</th><th class="num">Money in</th><th class="num">Money out</th></tr></thead><tbody>
        ${d.totals.map(t => `<tr class="${t.bold ? "bk-sum" : ""}"><td>${esc(t.label)}</td><td class="num">${t.bold ? amt(t.in) : amt(t.in, "item")}</td><td class="num">${t.bold ? amt(t.out) : amt(t.out, "item")}</td></tr>`).join("")}</tbody></table></div>` : ""}
      <div class="note"><b>${esc(d.tot_line)}</b></div>
      <h3>4 ${esc(d.gl_head)}</h3>${d.gl.map(t => `<div class="note">${esc(t)}</div>`).join("")}
      <h3>5 Sign-off note</h3>${d.note.map(t => `<div class="note">${esc(t)}</div>`).join("")}<div class="note muted">${esc(d.note_foot)}</div>
      <h3>6 Prepared by and Reviewed by</h3><div class="note">${esc(d.sign_text)}</div>
      <div class="bk-signers">${d.signers.map(x => `<div><b>${esc(x.role)}</b><div>Name: ${esc(x.name || "—")}</div><div class="muted small">${esc(x.note)}</div></div>`).join("")}</div>
      <div class="note muted">${esc(d.prep_line)}</div></div>
    <div class="note">${esc(d.file)} · until approvals can read the code, file the signed copy on the month's bank reconciliation checklist item (Upload the signed statement, under the month's sign-off).</div></div>`;
  $("#bk-print-h")?.focus?.({ preventScroll: true });
}

/* ---- the review of one statement ---- */
const RV = () => state.recon.rv;

function openReview(sid, scroll = true) { return pageDraw("bank", page => reviewOpen(page, sid, scroll)); }
async function reviewOpen(page, sid, scroll) {
  const d = await page.read(api(rcUrl("review", `&statement_id=${sid}`)));
  // A locked month, or one with nothing left to explain, opens with its matched lines shown (BankReview's savings state).
  const V = state.recon.rv = { sid, d, sel: {}, choice: {}, keep: {}, checked: false, why: {},
    showMatched: !!d.summary.locked || !d.lines.some(l => l.state === "open") };
  for (const l of d.lines) if (l.state === "open" && l.suggestions.length) V.choice[l.id] = "p:" + l.suggestions[0].payment_id;
  drawReview();
  if (scroll) $("#stmtList")?.scrollIntoView?.({ block: "start" });  // the review replaces the year view, lower on the page
}

// reset false (the page redrew after a one-line action): the rows chosen, their date ticks, the check tick and the
// descriptions typed stay for lines that are as they were.
function reloadReview(reset = true) { return pageDraw("bank", page => reviewReload(page, reset)); }
async function reviewReload(page, reset) {
  const V = RV();
  if (!V) return;
  const d = await page.read(api(rcUrl("review", `&statement_id=${V.sid}`)));
  const typed = [...document.querySelectorAll("[data-rv-desc],[data-rv-cat],[data-rv-note]")].map(el => [el.matches("[data-rv-desc]") ? "desc" : el.matches("[data-rv-cat]") ? "cat" : "note", el.dataset.rvDesc || el.dataset.rvCat || el.dataset.rvNote, el.value]);
  const was = Object.fromEntries(V.d.lines.map(l => [l.id, l.state + ":" + l.payment?.id]));
  if (reset) { V.sel = {}; V.keep = {}; V.checked = false; }
  else for (const l of d.lines) if (was[l.id] !== l.state + ":" + l.payment?.id) { delete V.sel[l.id]; delete V.keep[l.id]; delete V.choice[l.id]; }
  V.d = d;
  for (const l of d.lines) {
    if (l.state !== "open") delete V.choice[l.id];
    else if (!V.choice[l.id] && l.suggestions.length) V.choice[l.id] = "p:" + l.suggestions[0].payment_id;
  }
  drawReview();
  if (!reset) for (const [k, id, v] of typed) { const el = document.querySelector(`[data-rv-${k}="${id}"]`); if (el) el.value = v; }
}

// How far the bank date of a line is from the date the books hold for the payment p: {days, date, kind}, or null.
function rvGap(line, p) {
  if (!p) return null;
  const dates = p.voucher_dates?.length ? p.voucher_dates : p.typed_date ? [p.typed_date] : [];
  if (!dates.length) return null;
  const t = Date.parse(line.txn_date);
  const best = dates.map(x => ({ date: x, days: Math.abs(Math.round((Date.parse(x) - t) / 864e5)) })).sort((a, b) => a.days - b.days)[0];
  return best.days ? { ...best, kind: p.voucher_dates?.length ? "voucher" : "payment" } : null;
}
const rvPay = id => RV().d.payments.find(p => p.id === id);
// The date difference a row must have ticked before it can be applied: {days, date, kind} or null. A linked or
// explained line needs it only while the server says so (not once it is confirmed: it had its tick then).
function rvNeedsTick(l) {
  const V = RV();
  if (l.state !== "open") return l.needs_date_tick ? { days: l.gap_days, date: l.book_date, kind: l.book_date_kind } : null;
  const ch = V.choice[l.id];
  return ch?.startsWith("p:") ? rvGap(l, rvPay(+ch.slice(2))) : null;
}

function rvPayOption(p, sel, why) {
  return `<option value="p:${p.id}" ${sel === "p:" + p.id ? "selected" : ""}>${esc(p.description)} · ${p.direction === "in" ? "+" : ""}${money(p.amount, p.currency)} (${esc(monthName(p.month))})${why ? " · " + esc(why) : ""}${p.linked ? " · already linked " + money(p.linked, p.currency) : ""}</option>`;
}

// What an explained bank charge or bank profit still asks of SQL Account (a company kept there), in words.
function rvSqlNote(l, s) {
  if (!sqlTodo(s) || l.state !== "explained") return "";
  const t = `${l.note || ""} ${l.description}`.toLowerCase(), cur = s.account.currency;
  const kind = l.amount < 0 && t.includes("charge") ? "Bank charge" : l.amount > 0 && t.includes("profit") ? "Bank profit" : "";
  if (!kind) return "";
  const gl = s.bank_gl ? ` against ${s.bank_gl} ${s.account.label}` : "";
  return `${kind} of ${money(Math.abs(l.amount), cur)} on ${fmtDate(l.txn_date)}: enter it in SQL Account${gl}. Explaining it here doesn't post it.`;
}

function rvMine(l) {
  const V = RV(), s = V.d.summary, locked = s.locked;
  if (l.state !== "open") {
    const cur = s.account.currency, g = l.group;
    const chips = g ? g.map(p => `<span class="chip">${esc(p.description)} · ${money(Math.abs(p.part), p.currency).replace(/^\S+ /, "")}</span>`).join(" ")
      : l.vouchers.map(x => `<span class="chip">${esc(x.doc_no)} · ${shortDate(x.doc_date)}</span>`).join(" ");
    const sqlNote = rvSqlNote(l, s);
    const short = l.short ? `<div class="banner warn bk-short"><span>Matched, but the amounts differ. ${g.length === 1 ? "The payment comes" : `The ${g.length} payments come`} to ${money(Math.abs(l.short.linked), cur)}, ${l.short.gap * Math.sign(l.amount) > 0
      ? `${money(Math.abs(l.short.gap), cur)} short of the line: undo, then link the rest with them.` : `${money(Math.abs(l.short.gap), cur)} over the line: undo, then link only the payments it paid.`}</span></div>` : "";
    return `<div class="rv-what">${g ? `<b>Linked to ${plural1(g.length, "payment")}</b> <span class="muted">${money(g.reduce((a, p) => a + Math.abs(p.part), 0), cur)} together · ${esc(monthName(g[0].month))}</span>`
      : l.payment ? `<b>${esc(l.payment.description)}</b> <span class="muted">${l.payment.direction === "in" ? "+" : ""}${money(l.payment.amount, l.payment.currency)} · ${esc(monthName(l.payment.month))}</span>`
      : `<b>No documents needed</b>${l.note ? ` <span class="muted">${esc(l.note)}</span>` : ""}`}</div>
      ${chips ? `<div class="row bk-chips">${chips}</div>` : ""}${short}
      ${sqlNote ? `<div class="note bk-sqlnote"><b>Enter this in SQL Account.</b> ${esc(sqlNote)}</div>` : ""}
      <div class="row" style="gap:6px">${l.confirmed_at ? `<span class="pill ok">Confirmed ${shortDate(l.confirmed_at)}</span>` : `<span class="pill warn">Matched, not confirmed</span>`}
      ${locked ? lockedPill() : `<button class="ghost small" data-unlink="${l.id}" aria-label="Undo the line of ${esc(shortDate(l.txn_date))} (${esc(signedAmt(l.amount, cur))})">Undo</button>`}</div>`;
  }
  const ch = V.choice[l.id] || "";
  const sugg = l.suggestions.map(x => ({ p: rvPay(x.payment_id), why: x.reason })).filter(x => x.p);
  const used = new Set(sugg.map(x => x.p.id));
  // A receipt or payment SQL posted to the bank in several lines is open while one of its lines isn't linked (a fee
  // line, money the other way, goes to the same document); any other goes the line's way and isn't covered yet.
  const others = V.d.payments.filter(p => !used.has(p.id) && (p.open_lines
    ? p.open_lines.some(x => Math.abs(x - l.amount) < 0.005) || (!p.linked && (p.bank_net > 0) === (l.amount > 0))
    : (p.direction === "in") === (l.amount > 0) && !(p.linked && p.amount && p.linked >= p.amount - 0.005)));
  const opts = `<option value="">Choose what this is…</option>
    ${sugg.length ? `<optgroup label="Suggested">${sugg.map(x => rvPayOption(x.p, ch, x.why)).join("")}</optgroup>` : ""}
    ${others.length ? `<optgroup label="Open payments">${others.map(p => rvPayOption(p, ch)).join("")}</optgroup>` : ""}
    <option value="c" ${ch === "c" ? "selected" : ""}>Create a payment for this line</option>
    <option value="n" ${ch === "n" ? "selected" : ""}>No documents needed (bank charge)</option>`;
  // Only the types going the line's way: Money received for money in, Other for money out unless changed.
  const dir = l.amount > 0 ? "in" : "out";
  const extra = ch === "c" ? `<input data-rv-desc="${l.id}" maxlength="120" placeholder="What was this payment for?" aria-label="Description of the payment to create">
      <select data-rv-cat="${l.id}" aria-label="Type of payment">${typeOptions(defaultType(dir), dir)}</select>`
    : ch === "n" ? `<input data-rv-note="${l.id}" maxlength="120" placeholder="Reason, e.g. bank charges" aria-label="Reason no documents are needed">
      ${sqlTodo(V.d.summary) ? `<div class="note bk-sqlnote">If it belongs in the books, enter it in SQL Account too. This only explains the line here.</div>` : ""}` : "";
  return `<div class="row" style="gap:6px"><span class="pill warn">To explain</span>
    <button class="ghost small" id="br-more-${l.id}" data-explain="${l.id}" ${locked ? "disabled" : ""}>More options</button></div>
    <select data-rv-choice="${l.id}" aria-label="What this bank line is" ${locked ? "disabled" : ""}>${opts}</select>${extra}`;
}

function rvRow(l) {
  const V = RV(), cur = V.d.summary.account.currency, tick = rvNeedsTick(l), locked = V.d.summary.locked;
  const open = l.state === "open", can = !locked && (!open || !!V.choice[l.id]);
  return `<div class="rv-row ${open ? "open" : ""}" id="rv-row-${l.id}">
    <div class="rv-mine">${rvMine(l)}
      ${locked ? "" : `<label class="row rv-select"><input type="checkbox" data-rv-sel="${l.id}" ${V.sel[l.id] ? "checked" : ""} ${can ? "" : "disabled"}> Select</label>`}
      ${tick && !locked ? `<label class="row rv-keep"><input type="checkbox" data-rv-keep="${l.id}" ${V.keep[l.id] ? "checked" : ""}><span>Bank date differs by ${dayCount(tick.days)}: keep the ${tick.kind} date (${shortDate(tick.date)})</span></label>` : ""}</div>
    <div class="rv-bank"><div class="row spread"><span class="mono">${fmtDate(l.txn_date)}</span><span class="eyebrow">${l.amount < 0 ? "Money out" : "Money in"}</span></div>
      <div class="num ${l.amount < 0 ? "" : "recv"}"><b>${signedAmt(l.amount, cur)}</b></div>
      <div class="line-desc">${esc(l.description.replaceAll(" | ", " · "))}</div>
      <div class="note">Balance ${money(l.balance, cur)}</div></div></div>`;
}

function rvLists() {
  const V = RV(), d = V.d, cur = d.summary.account.currency, locked = d.summary.locked;
  const text = l => bankText(l, cur);
  const open = listRows("bank", d.lines.filter(l => l.state === "open"), text), done = listRows("bank", d.lines.filter(l => l.state !== "open"), text);
  setCount("bank", open.length + done.length, d.lines.length);
  const totalMatched = d.lines.filter(l => l.state !== "open").length, unconf = d.lines.filter(l => l.state !== "open" && !l.confirmed_at).length;
  const shorts = d.lines.filter(l => l.short).length;
  return `${open.map(rvRow).join("") || `<div class="empty">${d.lines.some(l => l.state === "open") ? "No open line matches." : "Nothing left to explain."}</div>`}
    ${totalMatched ? `<div class="row spread rv-mhead"><button class="link" id="br-mtoggle" data-rv-toggle="1" aria-expanded="${V.showMatched}">${totalMatched} matched · ${V.showMatched ? "Hide" : "Show"}</button>
      <div class="row">${shorts ? `<span class="pill bad">Matched, but the amounts differ · ${shorts}</span>` : ""}${unconf ? `<span class="note">${unconf} not confirmed yet</span>` : `<span class="pill ok">All confirmed</span>`}
      <button class="ghost small" data-rv-confirm-all="1" ${unconf && !locked ? "" : "disabled"}>Confirm all matched</button></div></div>
      ${V.showMatched ? (done.map(rvRow).join("") || `<div class="empty">No matched line matches.</div>`) : ""}` : ""}`;
}
const drawRvList = () => { const el = $("#rvList"); if (el) { el.innerHTML = rvLists(); paintCount("bank"); paintBar(); } };
LIST_REDRAW.bank = drawRvList;

// The No money moved group: each pair of book entries that cancel out, with its documents, its net, its reason (filled in
// from the documents, editable) and a tick to confirm it. The sign-off waits until every pair is confirmed and nil.
function rvPairs() {
  const V = RV(), s = V.d.summary, prs = s.pairs || [], cur = s.account.currency, locked = s.locked;
  if (!prs.length) return "";
  const bad = prs.filter(p => !p.nil), open = prs.filter(p => p.nil && !p.confirmed_at);
  const sum = bad.length ? ["bad", `Not nil · ${bad.length}`] : open.length ? ["warn", `${open.length} to confirm`] : ["ok", "All confirmed"];
  const row = (p, i) => {
    const title = p.docs.map(d => d.ref || d.description).join(" and "), id = `br-pair-${i}`, why = V.why[p.key] ?? p.reason;
    const tickOff = locked || !p.nil;
    return `<div class="bk-pair ${p.confirmed_at ? "ok" : p.nil ? "warn" : "bad"}" id="${id}" role="group" aria-label="Pair ${esc(title)}, ${p.nil ? "net nil" : `net ${esc(money(Math.abs(p.net), cur))}, not nil`}, ${p.confirmed_at ? "confirmed" : "not confirmed"}">
      <div class="row spread"><b>${esc(title)}</b><div class="row"><span class="pill ${p.nil ? "ok" : "bad"}">${icon(p.nil ? "check" : "alert")}${p.nil ? "Net nil" : `Net ${esc(money(Math.abs(p.net), cur))}, not nil`}</span>
        <span class="pill ${p.confirmed_at ? "ok" : p.nil ? "warn" : "bad"}">${p.confirmed_at ? `Confirmed ${esc(shortDate(p.confirmed_at))}` : p.nil ? "To confirm" : "Not nil"}</span></div></div>
      <div class="tbl-wrap"><table><caption class="sr-only">The book entries of the pair ${esc(title)}, with their amounts</caption><thead><tr><th>Document</th><th>Date</th><th>Description</th><th class="num">Money in</th><th class="num">Money out</th></tr></thead><tbody>
        ${p.docs.map(d => `<tr><td class="mono">${esc(d.ref || "—")}</td><td>${esc(shortDate(d.date))}</td><td>${esc(d.description)}</td><td class="num">${d.amount > 0 ? "+" + money(d.amount, cur).replace(/^\S+ /, "") : ""}</td><td class="num">${d.amount < 0 ? "−" + money(-d.amount, cur).replace(/^\S+ /, "") : ""}</td></tr>`).join("")}</tbody></table></div>
      <label class="field"><span>Reason <span class="muted">Filled in from the documents; kept with the sign-off</span></span>
        <input id="${id}-why" data-pair-why="${esc(p.key)}" maxlength="300" value="${esc(why)}" ${locked || p.confirmed_at ? "readonly" : ""} aria-describedby="${id}-err"></label>
      <div class="note bad-text" id="${id}-err" role="alert"></div>
      ${p.nil ? "" : `<div class="note bad-text" id="${id}-nil">The two entries don't cancel: ${esc(money(Math.abs(p.net), cur))} is left. A pair that isn't nil can't be confirmed, and the remainder stays a difference to explain until the entry is corrected${s.uses_sql ? " in SQL Account" : ""}.</div>`}
      <label class="row bk-tick"><input type="checkbox" id="${id}-tick" data-pair-tick="${esc(p.key)}" ${p.confirmed_at ? "checked" : ""} ${tickOff ? "disabled" : ""} ${p.nil ? "" : `aria-describedby="${id}-nil"`}> Confirmed: no money moved</label>
      ${s.uses_sql && s.source === "sql" ? `<div class="note">In SQL Account the pair stays in the books: tick both ${esc(title)} as cleared in ${esc(s.label)} in SQL's bank reconciliation, so its clearing report agrees.</div>` : ""}</div>`;
  };
  return `<div class="bk-pairs"><div class="row spread"><h3>No money moved · ${plural1(prs.length, "pair")}</h3><span class="pill ${sum[0]}">${esc(sum[1])}</span></div>
    <div class="note">Book entries${s.bank_gl ? ` on ${esc(s.bank_gl)}` : ""} that cancel each other out and never touched the bank, such as a reversal, or a duplicated self-billed e-Invoice whose payment voucher was recorded twice and refunded by an official receipt. The reconciliation statement lists them as pairs and leaves them out of its totals check. Check each reason, then tick the pair. The sign-off waits until every pair is confirmed and nil.</div>
    ${prs.map(row).join("")}</div>`;
}

async function pairTick(t) {
  const V = RV(), s = V.d.summary, key = t.dataset.pairTick, p = s.pairs.find(x => x.key === key);
  if (!p) return;
  const box = t.closest(".bk-pair"), why = box?.querySelector("[data-pair-why]")?.value.trim() ?? p.reason, err = box?.querySelector('[role="alert"]');
  const on = t.checked, title = p.docs.map(d => d.ref || d.description).join(" and ");
  if (on && !why) { t.checked = false; if (err) err.textContent = "Give the pair a reason first: it is kept with the sign-off."; box?.querySelector("[data-pair-why]")?.focus(); return; }
  const send = (confirmed, reason) => api("/api/recon/pair", { json: { entity_id: state.entity, account_id: s.account.id, month: s.month, key, reason, confirmed } });
  const again = bankAgain(false);
  try { await send(on, why); }
  catch (e) {
    t.checked = !on;
    // under the pair while it is still on show; left, or being read again, said in a message
    if (err && err.isConnected !== false && pageWhole()) err.textContent = changeError(e); else toast(`Pair ${title}: ${changeError(e)}`, true);
    return;
  }
  delete V.why[key];
  toast(on ? `Pair confirmed: ${title}, no money moved.` : `Pair no longer confirmed: ${title}.`, false, { undo: async () => {
    const after = bankAgain(false);
    await send(!on, why); toast(on ? "Undone. The pair is waiting to be confirmed." : "Undone. The pair is confirmed again."); await afterSaved(after);
  } });
  await afterSaved(again);
  document.querySelector(`[data-pair-tick="${typeof CSS !== "undefined" && CSS.escape ? CSS.escape(key) : key}"]`)?.focus?.();
}

// The bar at the foot of the review: what is selected, what is left, the difference once the rows are applied.
function paintBar() {
  const V = RV(); if (!V) return;
  const d = V.d, s = d.summary, cur = s.account.currency;
  const picked = d.lines.filter(l => V.sel[l.id]), open = d.lines.filter(l => l.state === "open");
  const left = open.filter(l => !V.sel[l.id]).length;
  // Creating a payment, or linking one the books don't date in this month, adds it to the books of a company not in SQL.
  let after = s.difference;
  if (after != null && !s.uses_sql) {
    for (const l of picked) {
      const ch = V.choice[l.id];
      if (l.state !== "open") continue;
      const p = ch?.startsWith("p:") ? rvPay(+ch.slice(2)) : null;
      if (ch === "c") after -= l.amount;
      else if (p && !(p.paid_date || "").startsWith(s.month)) after -= (p.direction === "in" ? 1 : -1) * (p.amount ?? Math.abs(l.amount));
    }
  }
  const bar = $("#rvBar"), sum = $("#rvSelected");
  if (sum) sum.innerHTML = `<b>${picked.length}</b><span>Selected · ${money(picked.reduce((a, l) => a + l.amount, 0), cur)}</span>`;
  if (!bar) return;
  if (s.locked) { bar.hidden = true; return; }
  bar.hidden = false;
  bar.innerHTML = `<div><b>${picked.length}</b> selected · <b>${left}</b> still to explain</div>
    <div>Difference after applying: <b class="${after == null ? "" : Math.abs(after) < 0.005 ? "recv" : "bad-text"}">${after == null ? "— (" + esc(s.book.note || "no books") + ")" : money(after, cur)}</b></div>
    <label class="row"><input type="checkbox" id="rvChecked" ${V.checked ? "checked" : ""}> I've checked these rows</label>
    <button class="btn" id="rvApply" ${picked.length ? "" : "disabled"}>Apply selected (${picked.length})</button>
    <div class="note rv-nosql">Applying only links, creates payments or explains lines here. Nothing is posted to SQL Account.</div>`;
}

function drawReview() {
  const V = RV(), box = $("#stmtList");
  if (!box || !V) return;
  const d = V.d, s = d.summary, cur = s.account.currency, st = s.statement, e = ent();
  const diff = s.difference, open = d.lines.filter(l => l.state === "open").length;
  box.innerHTML = `<div class="card"><div class="row spread"><div><div class="row bk-co"><span class="eyebrow">${esc(s.account.label)}</span><span class="pill grey">${icon(e.uses_sql ? "database" : "books")}${esc(keptLabel(e))}</span></div><h2 id="br-title">${esc(s.label)} statement · review</h2></div>
      <div class="row noprint"><button class="ghost small" data-rv-back="1">← Back to the year</button>${st.document_id ? `<a class="ghost small" href="/api/documents/${st.document_id}/file" target="_blank" rel="noopener">Statement PDF</a>` : ""}
      <a class="ghost small" href="${reconXlsx(s)}">${icon("sheet")}Excel</a></div></div>
      ${desktopNote("The bank review", "The review sets each statement line beside the payment it is matched to, which needs a wide screen.")}
      ${s.locked ? `<div class="banner grey bk-locked" role="status">${icon("lock")}<div><b>${esc(s.label)} is marked reconciled and locked.</b> <span>Its lines can't be linked, explained, confirmed or undone. Reopen the month to change anything.</span></div>
        <button type="button" class="ghost small" data-rc-reopen="${st.id}" aria-label="Reopen ${esc(s.label)} (it asks for a reason)">Reopen month</button></div>` : ""}
      <div class="stats">
        <div class="stat"><b>${d.lines.length}</b><span>Bank lines · ${open} to explain</span></div>
        <div class="stat"><b>${bookCell(s.book, cur)}</b><span>Book closing</span></div>
        <div class="stat"><b>${money(st.closing, cur)}</b><span>Bank closing${diff == null ? "" : " · difference " + money(diff, cur)}</span></div>
        <div class="stat" id="rvSelected"></div></div>
      <div class="row spread"><div>${rcPill(s.status, s.status_text)}${s.locked ? " " + lockedPill() : ""}</div></div>
      ${rcSqlCheck(s)}${s.listing_note ? `<div class="note">${esc(s.listing_note)}</div>` : ""}
      ${listBar("bank", "statement lines")}
      <div class="row rv-sortbar noprint"><span class="muted small">Sort by</span><table class="rv-sort"><thead><tr>${sortTh("bank", "date", "Date")}${sortTh("bank", "desc", "Description")}${sortTh("bank", "amount", "Amount", "num")}${sortTh("bank", "by", "Explained by")}</tr></thead></table></div>
      <div class="rv-wrap"><div id="rvList" class="rv-list">${rvLists()}</div>
        ${rvPairs()}
        <div class="rv-bar noprint" id="rvBar"></div></div>
      ${signBlock(s)}
      <div class="note">${signFoot()}</div></div>`;
  paintCount("bank"); paintBar();
}

// Applies the rows selected on the review screen (one request: all of them or none).
async function rvApply() {
  const V = RV(), rows = [];
  for (const l of V.d.lines) {
    if (!V.sel[l.id]) continue;
    const r = { line_id: l.id }, ch = V.choice[l.id] || "";
    if (l.state === "open") {
      if (ch === "c") {
        const desc = document.querySelector(`[data-rv-desc="${l.id}"]`)?.value.trim();
        if (!desc) throw new Error(`Give the payment for the line of ${shortDate(l.txn_date)} a description.`);
        r.create_payment = { description: desc, category: document.querySelector(`[data-rv-cat="${l.id}"]`)?.value || defaultType(l.amount > 0 ? "in" : "out") };
      } else if (ch === "n") { r.no_docs = true; r.note = document.querySelector(`[data-rv-note="${l.id}"]`)?.value.trim() || ""; }
      else if (ch.startsWith("p:")) r.payment_id = +ch.slice(2);
      else throw new Error(`Choose what the line of ${shortDate(l.txn_date)} is, or untick it.`);
    }
    if (rvNeedsTick(l)) r.keep_date = !!V.keep[l.id];
    rows.push(r);
  }
  const again = bankAgain();
  const r = await api("/api/recon/apply", { json: { entity_id: state.entity, statement_id: V.sid, checked: V.checked, rows } });
  // They are applied: nothing stays ticked, so Apply can't send them again while the review is read again (or if it can't be).
  Object.assign(V, { sel: {}, keep: {}, checked: false });
  if (RV() === V) drawRvList();
  toast(`Applied ${rows.length} row${rows.length === 1 ? "" : "s"}: ${r.linked} linked, ${r.created} created, ${r.explained} explained, ${r.confirmed} confirmed.`);
  return afterSaved(again);
}

// Sign-off actions (from the month panel or the review): ask the server, then draw the screen that was open again.
async function rcAct(path, body, done) {
  const again = bankAgain();
  await api(`/api/recon/${path}`, { json: { entity_id: state.entity, ...body } });
  toast(done);
  return afterSaved(again);
}

// The dialog of the one-line actions (link one payment or several, create a payment, no documents), kept beside the
// review's dropdown; the line stays to confirm. amount: the line's, signed as on the statement (money in above 0).
// Several payments paid together under one bank reference (a bulk transfer) are ticked together: their open amounts
// add up to a running total against the line.
function explainLine(lineId) {
  const V = RV(), l = V?.d.lines.find(x => x.id === lineId);
  if (!l || V.d.summary.locked) return;
  const cur = V.d.summary.account.currency, amount = l.amount, lineAbs = Math.abs(amount);
  const first = String(V.choice[l.id] || "").startsWith("p:") ? +V.choice[l.id].slice(2) : null;
  const pick = { sels: first ? [first] : [], cur: first, q: "", all: false };
  // Money in is most likely a receipt, money out a one-off payment; only the types going the line's way are offered.
  const dir = amount > 0 ? "in" : "out";
  state.drawerDirty = null;
  $("#drawer").innerHTML = `
    <div class="ex-head"><div class="row spread"><h2>Explain bank line</h2><button class="ghost small" id="closeDrawer">Close</button></div>
      <div class="muted small">${esc(V.d.summary.account.label)} · ${esc(V.d.summary.label)}</div>
      <div class="ex-line"><div class="row spread"><span class="muted">${shortDate(l.txn_date)} · ${amount > 0 ? "Money in" : "Money out"}</span><b class="mono">${money(lineAbs, cur)}</b></div>
        <div>${esc(l.description)}</div><div class="note">Balance ${money(l.balance, cur)}</div></div></div>
    <div class="card"><h3>Link to existing payments</h3>
      <div class="note">Choose one payment, or several paid together under one bank reference (a bulk transfer, say). The running total below shows how close they come to the line's amount.</div>
      <input id="ex-q" type="search" placeholder="Search by name or amount" autocomplete="off" aria-label="Search payments">
      <div class="note" id="ex-count"></div>
      <div class="ex-list" id="ex-list" role="listbox" aria-multiselectable="true" aria-label="Payments"></div>
      <label class="row ex-all"><input type="checkbox" id="ex-all"><span>Also show money the other way and payments already covered</span></label>
      <div class="bk-run" id="ex-run" aria-live="polite"></div>
      <div class="note">One payment can also be linked to several lines, e.g. a 25,000 fee sent as 5,000 + 10,000 + 10,000.</div>
      <div class="note bad-text" id="ex-err" role="alert"></div>
      <button class="btn" id="ex-link">Link</button></div>
    <div class="card"><h3>Create a new payment for this line</h3>
      <div class="note">For one-off transactions such as web hosting, flights or receipts.</div>
      <label class="field"><span>Description</span><input id="ex-desc"></label>
      <label class="field"><span>Type</span><select id="ex-cat">${typeOptions(defaultType(dir), dir)}</select></label>
      <button class="btn" id="ex-create">Create payment and link</button></div>
    <div class="card"><h3>No documents needed</h3>
      ${sqlTodo(V.d.summary) ? `<div class="note">For a bank charge or bank profit, enter it in SQL Account too: this only explains the line here, and the books agree with the bank once SQL has it.</div>` : ""}
      <label class="field"><span>Reason</span><input id="ex-note" placeholder="e.g. bank charges, own-account transfer"></label>
      <button class="ghost" id="ex-none">Mark as no documents needed</button></div>`;
  showDrawer();
  let rows = [];
  const openOf = r => r.open ?? r.p.amount ?? 0;
  const paint = () => {
    rows = LT.linkList(l, V.d.payments, pick.q, pick.all);
    $("#ex-count").textContent = `${rows.length} payment${rows.length === 1 ? "" : "s"}${pick.q ? " found" : ", likeliest first"}`;
    const shown = rows.some(r => r.p.id === pick.cur);
    $("#ex-list").innerHTML = rows.map((r, i) => { const on = pick.sels.includes(r.p.id);
      return `<button type="button" class="ex-pay ${on ? "on" : ""}" role="option" aria-selected="${on}" id="br-opt-${r.p.id}" tabindex="${pick.cur === r.p.id || (!shown && i === 0) ? 0 : -1}" data-ex-pay="${r.p.id}">
        <span class="ex-desc"><span class="bk-box" aria-hidden="true">${on ? icon("check") : ""}</span>${esc(r.p.description)}</span><span class="mono ex-amt">${r.p.direction === "in" ? "+" : ""}${money(r.p.amount, r.p.currency)}</span>
        <span class="ex-meta">${esc(monthName(r.p.month))}${r.p.linked ? ` · ${money(r.open, r.p.currency)} still open` : ""}${r.sugg ? ` · <b>Suggested</b>: ${esc(r.sugg.reason)}` : r.exact ? ` · <b>Same amount</b>` : ""}</span></button>`; }).join("")
      || `<div class="note">No payment matches. Try a shorter search, or create a new payment below.</div>`;
    const all = V.d.payments.filter(p => pick.sels.includes(p.id));
    const sum = Math.round(all.reduce((a, p) => a + (p.amount == null ? 0 : p.amount - (p.linked || 0)), 0) * 100) / 100, gap = Math.round((lineAbs - sum) * 100) / 100;
    const n = pick.sels.length;
    $("#ex-run").className = `bk-run${n && Math.abs(gap) > 0.005 ? " warn" : ""}`;
    $("#ex-run").innerHTML = n ? `<div class="row spread"><b>${n} selected</b><span class="mono">${money(sum, cur)} of the line's ${money(lineAbs, cur)}</span></div>
      <div class="${Math.abs(gap) <= 0.005 ? "recv" : "warn-text"}">${Math.abs(gap) <= 0.005 ? "Adds up" : gap > 0 ? money(gap, cur) + " short" : money(-gap, cur) + " over"}</div>
      ${n > 1 && Math.abs(gap) > 0.005 ? `<div class="note">You can still link them: the line then shows under "Matched, but the amounts differ" on the month until the rest is linked.</div>` : ""}` : "";
    $("#ex-link").textContent = n === 0 ? "Link" : n === 1 ? "Link 1 payment" : `Link ${n} payments`;
  };
  paint();
  const toggle = id => { pick.sels = pick.sels.includes(id) ? pick.sels.filter(x => x !== id) : [...pick.sels, id]; pick.cur = id; $("#ex-err").textContent = ""; paint(); document.getElementById(`br-opt-${id}`)?.focus(); };
  $("#ex-q").oninput = e => { pick.q = e.target.value; paint(); };
  $("#ex-q").onkeydown = e => { if (e.key === "ArrowDown" && rows.length) { e.preventDefault(); document.getElementById(`br-opt-${(rows.find(r => r.p.id === pick.cur) || rows[0]).p.id}`)?.focus(); } };
  $("#ex-all").onchange = e => { pick.all = e.target.checked; paint(); };
  $("#ex-list").onclick = e => { const b = e.target.closest("[data-ex-pay]"); if (b) toggle(+b.dataset.exPay); };
  // Arrow keys move between the payments, Home and End to the ends; Space or Enter ticks or unticks the one focused.
  $("#ex-list").onkeydown = e => {
    if (!rows.length) return;
    const at = rows.findIndex(r => `br-opt-${r.p.id}` === document.activeElement?.id);
    if (e.key === " " || e.key === "Enter") { e.preventDefault(); toggle(rows[Math.max(0, at)].p.id); return; }
    const j = e.key === "ArrowDown" ? Math.min(rows.length - 1, at + 1) : e.key === "ArrowUp" ? Math.max(0, at - 1) : e.key === "Home" ? 0 : e.key === "End" ? rows.length - 1 : null;
    if (j === null) return;
    e.preventDefault(); pick.cur = rows[j].p.id; paint(); document.getElementById(`br-opt-${pick.cur}`)?.focus();
  };
  const done = async (body, msg) => {
    const here = dialogHere();
    try { await api(`/api/statement-lines/${lineId}`, { json: body }); } catch (e) { return toast(changeError(e), true); }
    if (here()) await closeDrawer();
    toast(msg || "Line explained", false, { undo: async () => {
      await api(`/api/statement-lines/${lineId}`, { json: { payment_id: null } }); toast("Undone. The line is waiting to be explained."); await afterSaved(render); } });
    await afterSaved(render);
  };
  $("#ex-link").onclick = () => !pick.sels.length ? ($("#ex-err").textContent = "Choose a payment from the list first.")
    : done(pick.sels.length === 1 ? { payment_id: pick.sels[0] } : { payment_ids: pick.sels }, pick.sels.length > 1 ? `Line linked to ${pick.sels.length} payments.` : "Line explained");
  $("#ex-create").onclick = () => { if (!$("#ex-desc").value.trim()) return toast("Give the payment a description.", true); done({ create_payment: { description: $("#ex-desc").value.trim(), category: $("#ex-cat").value } }); };
  $("#ex-none").onclick = () => done({ status: "no_docs", note: $("#ex-note").value.trim() });
}

// A pair's reason typed stays when the review is drawn again; typing a reason for reopening clears the refusal shown.
document.addEventListener("input", ev => {
  const t = ev.target, k = t?.dataset?.pairWhy;
  if (k != null && RV()) { RV().why[k] = t.value; const err = t.closest?.(".bk-pair")?.querySelector('[role="alert"]'); if (err) err.textContent = ""; }
  if (t?.id === "bk-why") { const err = $("#bk-why-err"); if (err) err.textContent = ""; t.removeAttribute?.("aria-invalid"); }
});
