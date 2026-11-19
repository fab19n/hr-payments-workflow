"use strict";
/* ---------------- Bank statements ---------------- */
// The year view of one account (a row per month), a month's panel opened in place, and the review of a statement's lines.
// What matches, what is in the books and whether a month can be signed off is worked out by the server (hrp/recon.py);
// nothing here posts anything to SQL Account.
const RC_PILL = { to_import: "grey", to_review: "warn", difference: "bad", reconciled: "ok" };
const rcPill = (status, text) => `<span class="pill ${RC_PILL[status] || "grey"}">${esc(text)}</span>`;
const rcUrl = (what, extra = "") => `/api/recon/${what}?entity_id=${state.entity}${extra}`;
const signedAmt = (n, cur) => `${n < 0 ? "−" : "+"}${money(Math.abs(n), cur).replace(/^\S+ /, "")}`;
const dayCount = n => `${n} day${n === 1 ? "" : "s"}`;
const bankText = (l, cur) => [fmtDate(l.txn_date), l.txn_date, l.description, LT.amount(l.amount), cur, l.payment_desc, l.note, l.status === "no_docs" ? "no documents needed" : l.payment_id ? "" : "not explained"].join(" ");

// The books' side of a month as one cell: the balance, or why there is none.
const bookCell = (b, cur) => b.closing != null ? money(b.closing, cur) : `<span class="muted">${esc(b.note || "—")}</span>`;

// Sign-off controls for a month (s: the month's summary), the same in its panel and at the foot of its review.
function signBlock(s) {
  if (!s.statement) return "";
  const id = s.statement.id;
  if (s.reconciled_at) {
    return `<div class="rc-sign"><span class="pill ok">Reconciled ${fmtDate(s.reconciled_at)}${s.reconciled_how === "before tracking" ? " · before tracking" : ""}</span>
      ${s.reconciled_note ? `<span class="note">${esc(s.reconciled_note)}</span>` : ""}
      <button class="ghost small" data-rc-undo="${id}">Undo sign-off</button></div>${rcChanged(s)}`;
  }
  const why = s.why_not.length ? `<div class="note">Not ready: ${esc(s.why_not.join("; "))}.</div>` : "";
  const before = s.before_tracking ? `<div class="rc-before"><div class="note">This month is before tracking began here. If it was reconciled outside this app, say so.</div>
      <label class="field"><span>How it was reconciled${s.book_matches ? " (optional: the books agree with the bank)" : ""}</span><input data-rc-note="${id}" maxlength="200" placeholder="e.g. reconciled in SQL Account in August"></label>
      <label class="row"><input type="checkbox" data-rc-before-tick="${id}"> This month was reconciled before tracking began</label>
      <button class="ghost" data-rc-before="${id}" ${s.can_sign_before_tracking ? "" : "disabled"}>Reconciled before tracking</button>
      ${s.can_sign_before_tracking ? "" : `<div class="note">The statement has to add up first.</div>`}</div>` : "";
  return `<div class="rc-sign"><button class="btn" data-rc-sign="${id}" ${s.can_sign ? "" : "disabled"}>Mark reconciled</button>${why}</div>${before}`;
}

// A month signed off before SQL's receipts and payments counted by their lines on the bank, whose book figures that
// changed: the figures then and now, and the owner's confirmation asked for (the sign-off stays until then).
function rcChanged(s) {
  const ch = s.book_changed;
  if (!ch || !s.statement) return "";
  const cur = s.account.currency, row = (k, w) => `<tr><td>${w}</td><td class="num">${money(ch.old[k], cur)}</td><td class="num">${money(ch.new[k], cur)}</td></tr>`;
  return `<div class="banner warn rc-changed"><b>${esc(ch.text)}</b>
    <span>SQL's receipts and payments now count by what each one posted to the bank account, not by its listing amount.</span>
    <div class="tbl-wrap"><table><thead><tr><th></th><th class="num">At sign-off</th><th class="num">Now</th></tr></thead><tbody>
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

function rcTable(title, rows, cur) {
  if (!rows.length) return "";
  return `<div class="tbl-wrap"><h3>${esc(title)} · ${rows.length}</h3><table><thead><tr><th>Date</th><th>Description</th><th class="num">Amount</th><th>Why</th></tr></thead><tbody>
    ${rows.map(x => `<tr><td class="mono">${shortDate(x.date)}</td><td class="line-desc">${x.ref ? `<b>${esc(x.ref)}</b> ` : ""}${esc((x.description || "").replaceAll(" | ", " · "))}</td>
      <td class="num">${signedAmt(x.amount, cur)}</td><td class="note">${esc(x.why)}</td></tr>`).join("")}</tbody></table></div>`;
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
      ${st.adds_up ? "" : `<span class="pill bad">Statement doesn't add up</span>`}</div>
      <div class="row">${st.document_id ? `<a class="ghost small" href="/api/documents/${st.document_id}/file" target="_blank">Statement PDF</a>` : ""}
      <button class="btn small" data-rc-review="${st.id}">Review lines</button></div></div>
    <h3>Reconciliation statement</h3>
    ${s.book.state !== "ok" ? `<div class="note">${esc(s.book.note)}${s.book.note === "Needs book opening" ? ": type this account's book balance under Book opening below." : " on the SQL import page."}</div>` : ""}
    ${diff != null && Math.abs(diff) >= 0.005 ? `<div class="note">The books are ${money(Math.abs(diff), cur)} ${diff > 0 ? "below" : "above"} the bank.${parts.length ? " That is: " + esc(parts.join("; ")) + "." : ""}</div>` : ""}
    ${rcTable("In the books, not on this statement", s.books_only, cur)}${rcTable("On the statement, not in the books", s.bank_only, cur)}
    ${s.differ.length ? `<div class="tbl-wrap"><h3>Matched, but the amounts differ · ${s.differ.length}</h3><table><thead><tr><th>Payment</th><th class="num">Books</th><th class="num">Statement</th><th class="num">Difference</th></tr></thead><tbody>
      ${s.differ.map(x => `<tr><td>${x.ref ? `<b>${esc(x.ref)}</b> ` : ""}${esc(x.description)}</td><td class="num">${money(x.book, cur)}</td><td class="num">${money(x.bank, cur)}</td><td class="num">${money(x.amount, cur)}</td></tr>`).join("")}</tbody></table></div>` : ""}
    ${!s.books_only.length && !s.bank_only.length && !s.differ.length && s.book.state === "ok" ? `<div class="note">Everything on the statement is in the books, and the other way round.</div>` : ""}
    ${gone ? `<div class="note">Not counted as bank movements: ${s.left_out.journals} journal${s.left_out.journals === 1 ? "" : "s"} and ${s.left_out.invoices} customer invoice${s.left_out.invoices === 1 ? "" : "s"} (customer refunds included) in the SQL listing. Fetch SQL's GL Journal of Transaction to count a journal that moves the bank.</div>` : ""}
    ${unk ? `<div class="note">Not counted: ${unk} cash book entr${unk === 1 ? "y" : "ies"} with no money in or out shown, so the books may differ by that amount.</div>` : ""}
    ${other ? `<div class="note">Not counted: ${plural(other, "receipt or payment", "receipts or payments")} whose lines in SQL don't touch this bank account (paid from another account).</div>` : ""}
    ${s.listing_note ? `<div class="note">${esc(s.listing_note)}</div>` : ""}
    ${s.uses_sql ? `<div class="note">For the reconciliation, fetch only the bank's cash book listing: a voucher paid from petty cash or a card would count as a bank movement.</div>` : ""}
    ${signBlock(s)}
    <div class="note">Marking a month reconciled is a record kept in this app. Nothing is posted to SQL Account.</div></div>`;
}

async function viewBank(main) {
  const e = ent(), R = state.recon;
  if (R.entity !== state.entity) Object.assign(R, { entity: state.entity, account: null, year: null, open: null, panel: null, rv: null });
  // Opened from Before you print or Next up: that account is shown, and with lines to explain its review opens.
  const focus = state.focusBank; state.focusBank = null;
  if (focus?.account && e.accounts.some(a => a.id === focus.account)) { if (R.account !== focus.account) R.rv = null; R.account = focus.account; }
  if (!e.accounts.some(a => a.id === R.account)) R.account = defaultAccount(e)?.id;
  if (focus && state.month) R.year = state.month.slice(0, 4);
  const acctOpts = pickAccounts(e, R.account).map(a => acctOption(a, R.account, true)).join("");
  main.innerHTML = `${entityPicker()}
    <div class="card"><h1>Bank statements</h1>
      <div class="note">Import each month's Maybank statement PDF. Every line is matched to a payment automatically where the payee and amount agree (split DuitNow transfers are added together). Then review the month: confirm what was matched, explain the rest, and mark the month reconciled once the books agree with the bank.</div>
      <form class="row" id="stmtForm"><label class="field"><span>Account</span><select id="stmtAcct">${acctOpts}</select></label>
      <label class="field"><span>Statement PDF</span><input id="stmtFile" type="file" accept=".pdf"></label>
      <button class="btn" type="submit" style="align-self:end">Import statement</button>
      <button class="ghost" type="button" id="rematch" style="align-self:end">Match again</button></form></div>
    <div id="stmtList"></div>`;
  await drawRecon(focus);
}

async function drawRecon(focus) {
  const R = state.recon, box = $("#stmtList");
  if (!box) return;
  if (R.rv) return reloadReview(false);
  const e = ent();
  const y = await api(rcUrl("year", `&account_id=${R.account}${R.year ? `&year=${R.year}` : ""}`));
  R.year = y.year; R.data = y;
  if (focus) {
    const row = y.rows.find(r => r.month === state.month && r.statement_id);
    if (row && state.bankOnly) return openReview(row.statement_id, false);  // the page is at the top already
    if (row) R.open = row.month;
  }
  R.panel = R.open && y.rows.some(r => r.month === R.open) ? await api(rcUrl("month", `&account_id=${R.account}&month=${R.open}`)) : null;
  const cur = y.account.currency;
  const rowHtml = r => `<tr class="${R.open === r.month ? "focus" : ""}"><td><button class="link" data-rc-open="${r.month}" aria-expanded="${R.open === r.month}">${esc(r.label)}</button></td>
      <td>${rcPill(r.status, r.status_text)}${r.book_changed ? `<div class="note bad-text">${esc(r.book_changed.text)}: book closing ${money(r.book_changed.old.closing, cur)} at sign-off, ${money(r.book_changed.new.closing, cur)} now (in ${money(r.book_changed.old.in, cur)} → ${money(r.book_changed.new.in, cur)}, out ${money(r.book_changed.old.out, cur)} → ${money(r.book_changed.new.out, cur)})</div>` : ""}</td>
      <td class="num">${r.bank_closing != null ? money(r.bank_closing, cur) : "—"}</td><td class="num">${bookCell({ closing: r.book_closing, note: r.book_note }, cur)}</td>
      <td>${r.reconciled_at ? fmtDate(r.reconciled_at) + (r.reconciled_how === "before tracking" ? ` <span class="muted">· before tracking</span>` : "") : "—"}</td>
      <td class="noprint">${r.document_id ? `<a href="/api/documents/${r.document_id}/file" target="_blank">PDF</a>` : "—"}</td></tr>
      ${R.open === r.month && R.panel ? `<tr class="panelrow"><td colspan="6">${monthPanel(R.panel)}</td></tr>` : ""}`;
  const openings = y.openings.map(o => `${monthName(o.month)}: ${money(o.amount, cur)}`).join(" · ");
  const firstMonth = y.openings[0]?.month || y.rows.filter(r => r.statement_id).map(r => r.month).sort()[0] || y.rows.map(r => r.month).sort()[0] || "";
  box.innerHTML = `<div class="card">
      <div class="row spread"><div><div class="eyebrow">${esc(e.name)}</div><h2>${esc(y.account.label)} · ${esc(y.year)}</h2></div>
      <div class="row noprint">${pickAccounts(e, R.account).length > 1 ? pickAccounts(e, R.account).map(a => `<button class="${a.id === R.account ? "btn" : "ghost"} small" data-rc-acct="${a.id}">${esc(a.label)}</button>`).join("") : ""}
      ${y.years.length > 1 ? y.years.map(yr => `<button class="${yr === y.year ? "btn" : "ghost"} small" data-rc-year="${yr}">${esc(yr)}</button>`).join("") : ""}</div></div>
      <div class="note">Click a month for its summary. Book closing comes from ${esc(y.source)}.</div>
      ${y.listing_note ? `<div class="note">${esc(y.listing_note)}</div>` : ""}
      <div class="tbl-wrap"><table><thead><tr><th>Month</th><th>Status</th><th class="num">Bank closing</th><th class="num">Book closing</th><th>Reconciled on</th><th class="noprint">Statement</th></tr></thead><tbody>
      ${y.rows.map(rowHtml).join("") || `<tr><td colspan="6" class="empty">No months to show for ${esc(y.year)}.</td></tr>`}</tbody></table></div></div>
    <div class="card noprint"><h2>Book opening</h2>
      <div class="note">The balance ${esc(y.account.label)} had in your books on the first day of its first month here${e.uses_sql ? " (your SQL Account bank balance)" : ""}. Type it once; each later month carries on from the month before. ${openings ? `Set so far: ${esc(openings)}.` : "None set yet, so book closing shows Needs book opening."}</div>
      <form class="row" id="openingForm"><label class="field"><span>Month it applies to</span><input id="openMonth" type="month" required value="${esc(firstMonth)}"></label>
      <label class="field"><span>Book balance (${esc(cur)})</span><input id="openAmount" inputmode="decimal" required placeholder="e.g. 25,367.58"></label>
      <button class="btn" type="submit" style="align-self:end">Save book opening</button></form></div>`;
}

/* ---- the review of one statement ---- */
const RV = () => state.recon.rv;

async function openReview(sid, scroll = true) {
  const d = await api(rcUrl("review", `&statement_id=${sid}`));
  const V = state.recon.rv = { sid, d, sel: {}, choice: {}, keep: {}, checked: false, showMatched: false };
  for (const l of d.lines) if (l.state === "open" && l.suggestions.length) V.choice[l.id] = "p:" + l.suggestions[0].payment_id;
  drawReview();
  if (scroll) $("#stmtList")?.scrollIntoView?.({ block: "start" });  // the review replaces the year view, lower on the page
}

// reset false (the page redrew after a one-line action): the rows chosen, their date ticks, the check tick and the
// descriptions typed stay for lines that are as they were.
async function reloadReview(reset = true) {
  const V = RV(), d = await api(rcUrl("review", `&statement_id=${V.sid}`));
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

function rvMine(l) {
  const V = RV();
  if (l.state !== "open") {
    const v = l.vouchers.map(x => `<span class="chip">${esc(x.doc_no)} · ${shortDate(x.doc_date)}</span>`).join(" ");
    return `<div class="rv-what">${l.payment ? `<b>${esc(l.payment.description)}</b> <span class="muted">${l.payment.direction === "in" ? "+" : ""}${money(l.payment.amount, l.payment.currency)} · ${esc(monthName(l.payment.month))}</span>`
      : `<b>No documents needed</b>${l.note ? ` <span class="muted">${esc(l.note)}</span>` : ""}`}</div>
      <div class="row" style="gap:6px">${v}${l.confirmed_at ? `<span class="pill ok">Confirmed ${shortDate(l.confirmed_at)}</span>` : `<span class="pill warn">Matched, not confirmed</span>`}
      <button class="ghost small" data-unlink="${l.id}">Undo</button></div>`;
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
    : ch === "n" ? `<input data-rv-note="${l.id}" maxlength="120" placeholder="Reason, e.g. bank charges" aria-label="Reason no documents are needed">` : "";
  return `<div class="row" style="gap:6px"><span class="pill warn">To explain</span>
    <button class="ghost small" data-explain="${l.id}">More options</button></div>
    <select data-rv-choice="${l.id}" aria-label="What this bank line is">${opts}</select>${extra}`;
}

function rvRow(l) {
  const V = RV(), cur = V.d.summary.account.currency, tick = rvNeedsTick(l);
  const open = l.state === "open", can = !open || !!V.choice[l.id];
  return `<div class="rv-row ${open ? "open" : ""}" id="rv-row-${l.id}">
    <div class="rv-mine">${rvMine(l)}
      <label class="row rv-select"><input type="checkbox" data-rv-sel="${l.id}" ${V.sel[l.id] ? "checked" : ""} ${can ? "" : "disabled"}> Select</label>
      ${tick ? `<label class="row rv-keep"><input type="checkbox" data-rv-keep="${l.id}" ${V.keep[l.id] ? "checked" : ""}><span>Bank date differs by ${dayCount(tick.days)}: keep the ${tick.kind} date (${shortDate(tick.date)})</span></label>` : ""}</div>
    <div class="rv-bank"><div class="row spread"><span class="mono">${fmtDate(l.txn_date)}</span><span class="eyebrow">${l.amount < 0 ? "Money out" : "Money in"}</span></div>
      <div class="num ${l.amount < 0 ? "" : "recv"}"><b>${signedAmt(l.amount, cur)}</b></div>
      <div class="line-desc">${esc(l.description.replaceAll(" | ", " · "))}</div>
      <div class="note">Balance ${money(l.balance, cur)}</div></div></div>`;
}

function rvLists() {
  const V = RV(), d = V.d, cur = d.summary.account.currency;
  const text = l => bankText(l, cur);
  const open = listRows("bank", d.lines.filter(l => l.state === "open"), text), done = listRows("bank", d.lines.filter(l => l.state !== "open"), text);
  setCount("bank", open.length + done.length, d.lines.length);
  const totalMatched = d.lines.filter(l => l.state !== "open").length, unconf = d.lines.filter(l => l.state !== "open" && !l.confirmed_at).length;
  return `${open.map(rvRow).join("") || `<div class="empty">${d.lines.some(l => l.state === "open") ? "No open line matches." : "Nothing left to explain."}</div>`}
    ${totalMatched ? `<div class="row spread rv-mhead"><button class="link" data-rv-toggle="1">${totalMatched} matched · ${V.showMatched ? "Hide" : "Show"}</button>
      <div class="row">${unconf ? `<span class="note">${unconf} not confirmed yet</span>` : `<span class="pill ok">All confirmed</span>`}
      <button class="ghost small" data-rv-confirm-all="1" ${unconf ? "" : "disabled"}>Confirm all matched</button></div></div>
      ${V.showMatched ? (done.map(rvRow).join("") || `<div class="empty">No matched line matches.</div>`) : ""}` : ""}`;
}
const drawRvList = () => { const el = $("#rvList"); if (el) { el.innerHTML = rvLists(); paintCount("bank"); paintBar(); } };
LIST_REDRAW.bank = drawRvList;

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
  bar.innerHTML = `<div><b>${picked.length}</b> selected · <b>${left}</b> still to explain</div>
    <div>Difference after applying: <b class="${after == null ? "" : Math.abs(after) < 0.005 ? "recv" : "bad-text"}">${after == null ? "— (" + esc(s.book.note || "no books") + ")" : money(after, cur)}</b></div>
    <label class="row"><input type="checkbox" id="rvChecked" ${V.checked ? "checked" : ""}> I've checked these rows</label>
    <button class="btn" id="rvApply" ${picked.length ? "" : "disabled"}>Apply selected (${picked.length})</button>
    <div class="note rv-nosql">Applying only links, creates payments or explains lines here. Nothing is posted to SQL Account.</div>`;
}

function drawReview() {
  const V = RV(), box = $("#stmtList");
  if (!box || !V) return;
  const d = V.d, s = d.summary, cur = s.account.currency, st = s.statement;
  const diff = s.difference, open = d.lines.filter(l => l.state === "open").length;
  box.innerHTML = `<div class="card"><div class="row spread"><div><div class="eyebrow">${esc(s.account.label)}</div><h2>${esc(s.label)} statement · review</h2></div>
      <div class="row noprint"><button class="ghost small" data-rv-back="1">← Back to the year</button>${st.document_id ? `<a class="ghost small" href="/api/documents/${st.document_id}/file" target="_blank">Statement PDF</a>` : ""}</div></div>
      <div class="stats">
        <div class="stat"><b>${d.lines.length}</b><span>Bank lines · ${open} to explain</span></div>
        <div class="stat"><b>${bookCell(s.book, cur)}</b><span>Book closing</span></div>
        <div class="stat"><b>${money(st.closing, cur)}</b><span>Bank closing${diff == null ? "" : " · difference " + money(diff, cur)}</span></div>
        <div class="stat" id="rvSelected"></div></div>
      <div class="row spread"><div>${rcPill(s.status, s.status_text)}</div></div>
      ${rcSqlCheck(s)}${s.listing_note ? `<div class="note">${esc(s.listing_note)}</div>` : ""}
      ${listBar("bank", "statement lines")}
      <div class="row rv-sortbar noprint"><span class="muted small">Sort by</span><table class="rv-sort"><thead><tr>${sortTh("bank", "date", "Date")}${sortTh("bank", "desc", "Description")}${sortTh("bank", "amount", "Amount", "num")}${sortTh("bank", "by", "Explained by")}</tr></thead></table></div>
      <div class="rv-wrap"><div id="rvList" class="rv-list">${rvLists()}</div>
        <div class="rv-bar noprint" id="rvBar"></div></div>
      ${signBlock(s)}
      <div class="note">Marking a month reconciled is a record kept in this app. Nothing is posted to SQL Account.</div></div>`;
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
  const r = await api("/api/recon/apply", { json: { entity_id: state.entity, statement_id: V.sid, checked: V.checked, rows } });
  toast(`Applied ${rows.length} row${rows.length === 1 ? "" : "s"}: ${r.linked} linked, ${r.created} created, ${r.explained} explained, ${r.confirmed} confirmed.`);
  return reloadReview();
}

// Sign-off actions (from the month panel or the review): ask the server, then draw the screen that was open again.
async function rcAct(path, body, done) {
  await api(`/api/recon/${path}`, { json: { entity_id: state.entity, ...body } });
  toast(done);
  if (state.recon.rv) return reloadReview();
  return drawRecon();
}

// The drawer of the one-line actions (link, create a payment, no documents), kept beside the review's dropdown; the line
// stays to confirm. amount: the line's, signed as on the statement (money in above 0).
function explainLine(lineId) {
  const V = RV(), l = V?.d.lines.find(x => x.id === lineId);
  if (!l) return;
  const cur = V.d.summary.account.currency, amount = l.amount;
  const pick = { id: String(V.choice[l.id] || "").startsWith("p:") ? +V.choice[l.id].slice(2) : null, q: "", all: false };
  // Money in is most likely a receipt, money out a one-off payment; only the types going the line's way are offered.
  const dir = amount > 0 ? "in" : "out";
  state.drawerDirty = null;
  $("#drawer").innerHTML = `
    <div class="ex-head"><div class="row spread"><h2>Explain bank line</h2><button class="ghost small" id="closeDrawer">Close</button></div>
      <div class="ex-line"><div class="row spread"><span class="muted">${shortDate(l.txn_date)} · ${amount > 0 ? "Money in" : "Money out"}</span><b class="mono">${money(Math.abs(amount), cur)}</b></div>
        <div>${esc(l.description)}</div><div class="note">Balance ${money(l.balance, cur)}</div></div></div>
    <div class="card"><h3>Link to an existing payment</h3>
      <input id="ex-q" type="search" placeholder="Search by name or amount" autocomplete="off" aria-label="Search payments">
      <div class="note" id="ex-count"></div>
      <div class="ex-list" id="ex-list" role="listbox" aria-label="Payments"></div>
      <label class="row ex-all"><input type="checkbox" id="ex-all"><span>Also show money the other way and payments already covered</span></label>
      <div class="note">One payment can be linked to several lines, e.g. a 25,000 fee sent as 5,000 + 10,000 + 10,000.</div>
      <button class="btn" id="ex-link">Link</button></div>
    <div class="card"><h3>Create a new payment for this line</h3>
      <div class="note">For one-off transactions such as web hosting, flights or receipts.</div>
      <label class="field"><span>Description</span><input id="ex-desc"></label>
      <label class="field"><span>Type</span><select id="ex-cat">${typeOptions(defaultType(dir), dir)}</select></label>
      <button class="btn" id="ex-create">Create payment and link</button></div>
    <div class="card"><h3>No documents needed</h3>
      <label class="field"><span>Reason</span><input id="ex-note" placeholder="e.g. bank charges, own-account transfer"></label>
      <button class="ghost" id="ex-none">Mark as no documents needed</button></div>`;
  $("#drawer").hidden = false;
  const paint = () => {
    const rows = LT.linkList(l, V.d.payments, pick.q, pick.all);
    $("#ex-count").textContent = `${rows.length} payment${rows.length === 1 ? "" : "s"}${pick.q ? " found" : ", likeliest first"}`;
    $("#ex-list").innerHTML = rows.map(r => `<button type="button" class="ex-pay ${r.p.id === pick.id ? "on" : ""}" role="option" aria-selected="${r.p.id === pick.id}" data-ex-pay="${r.p.id}">
        <span class="ex-desc">${esc(r.p.description)}</span><span class="mono ex-amt">${r.p.direction === "in" ? "+" : ""}${money(r.p.amount, r.p.currency)}</span>
        <span class="ex-meta">${esc(monthName(r.p.month))}${r.p.linked ? ` · ${money(r.open, r.p.currency)} still open` : ""}${r.sugg ? ` · <b>Suggested</b>: ${esc(r.sugg.reason)}` : r.exact ? ` · <b>Same amount</b>` : ""}</span></button>`).join("")
      || `<div class="note">No payment matches. Try a shorter search, or create a new payment below.</div>`;
  };
  paint();
  $("#ex-q").oninput = e => { pick.q = e.target.value; paint(); };
  $("#ex-all").onchange = e => { pick.all = e.target.checked; paint(); };
  $("#ex-list").onclick = e => { const b = e.target.closest("[data-ex-pay]"); if (b) { pick.id = +b.dataset.exPay; paint(); } };
  const done = async (body) => { try { await api(`/api/statement-lines/${lineId}`, { json: body }); closeDrawer(); toast("Line explained"); render(); } catch (e) { toast(e.message, true); } };
  $("#ex-link").onclick = () => pick.id ? done({ payment_id: pick.id }) : toast("Choose a payment first.", true);
  $("#ex-create").onclick = () => { if (!$("#ex-desc").value.trim()) return toast("Give the payment a description.", true); done({ create_payment: { description: $("#ex-desc").value.trim(), category: $("#ex-cat").value } }); };
  $("#ex-none").onclick = () => done({ status: "no_docs", note: $("#ex-note").value.trim() });
}

