"use strict";
/* ---------------- SQL Account exports ---------------- */
const SQL_FIELD_LABELS = { doc_no: "Doc No", date: "Date", description: "Description", payee: "Payee / name", amount: "Amount", debit: "Debit", credit: "Credit",
  einvoice: "e-Invoice UUID", doc_type: "Doc type", einvoice_status: "e-Invoice status", einvoice_link: "e-Invoice link",
  code: "SQL code", payment_method: "Payment method", cheque_no: "Cheque no.", dockey: "Doc key", currency_code: "Currency" };
// What SQL also says of an entry, under its payee: "Code 400-A001 · Chq 12345 · Method Maybank" (only what it has).
const sqlCodes = x => {
  const bits = [x.code && `Code ${x.code}`, x.cheque_no && `Chq ${x.cheque_no}`, x.payment_method && `Method ${x.payment_method}`].filter(Boolean);
  return bits.length ? `<div class="note">${esc(bits.join(" · "))}</div>` : "";
};
// The voucher numbers in a payment's SQL ref box, as the server reads them (sqlimport.refs_of).
const sqlRefs = t => (t || "").toUpperCase().split(/[,;\s]+/).filter(Boolean);

// The payments an SQL entry (x) can be linked to: those going the same way first (money out for a PV, money in for a
// receipt), and among them those that already have another voucher last and labelled, so adding a second one is a
// deliberate choice. The other way follows on its own, for a refund. sel: the payment chosen.
function paymentOptions(cands, x, sel) {
  const has = p => sqlRefs(p.sql_ref).filter(n => n !== x.doc_no.toUpperCase());
  const opts = list => [...list.filter(p => !has(p).length), ...list.filter(p => has(p).length)]
    .map(p => `<option value="${p.id}" ${p.id === sel ? "selected" : ""}>${esc(p.description)} · ${money(p.amount)}${has(p).length ? ` (already has ${esc(has(p).join(", "))})` : ""}</option>`).join("");
  const same = cands.filter(p => !x.direction || p.direction === x.direction), other = cands.filter(p => x.direction && p.direction !== x.direction);
  return opts(same) + (other.length
    ? `<optgroup label="${x.direction === "in" ? "Payments out (if this refunds one)" : "Money in (if this pays one back)"}">${opts(other)}</optgroup>` : "");
}
// The Import button's text: the entries not imported yet, and how many of them are linked.
const applyLabel = p => !p.records.filter(r => !r.exists).length && (p.ledger || p.myinvois)
  ? [p.ledger ? "Keep account lines" : "", p.myinvois ? "Keep MyInvois e-Invoices" : ""].filter(Boolean).join(" and ").replace(" and Keep", " and keep")
  : `Import ${p.records.filter(r => !r.exists).length} entries (${p.records.filter(r => (r.payment_id || r.task_id) && !r.exists || r.exists && r.kind === "invoice" && r.payment_id).length} linked)${p.ledger ? " and keep account lines" : ""}${p.myinvois ? " and keep MyInvois e-Invoices" : ""}`;
const GL_KIND = { journal: "GL Journal of Transaction", gl_ledger: "GL Ledger", trial_balance: "Trial Balance" };
const sen = n => n == null ? null : n / 100;

// The pill beside an SQL entry that says what SQL's Journal of Transaction gave for it (d.lines[entry id]); clicking
// it opens the lines under the row. "No lines" only shows when a journal read covered the entry's date and book.
function linesPill(lines, x) {
  const l = lines?.[x.id];
  if (!l) return "";
  if (!l.n) return ` <span class="pill grey">No lines</span>`;
  const [cls, text] = l.state === "gone" ? ["bad", "No longer in SQL"] : !l.balanced ? ["bad", "Lines don't balance"]
    : l.total_ok === false ? ["warn", "Lines ≠ amount"] : l.version > 1 ? ["warn", `Changed in SQL (v${l.version})`]
    : [l.unknown?.length || l.warnings ? "warn" : "ok", plural(l.n, "line")];
  return ` <button type="button" class="pill ${cls} pill-btn" data-sql-lines="${esc(x.doc_no)}" title="Show the account lines">${esc(text)}</button>`;
}

// One version of a document's account lines as a table: the bank's lines marked, a code the chart and the customers
// and suppliers don't know marked "Not in chart".
function ledgerLinesTable(v, banks) {
  const known = l => l.name_from === "chart" || l.name_from === "party" || l.control;
  return `<div class="tbl-wrap"><table class="sql-lines"><thead><tr><th>Account</th><th>Description</th><th class="num">Debit</th><th class="num">Credit</th></tr></thead><tbody>
    ${v.lines.map(l => `<tr class="${banks.includes(l.code) ? "sql-bank-line" : ""}"><td><span class="mono">${esc(l.code)}</span> ${esc(l.name || "")}${known(l) ? "" : ` <span class="pill warn">Not in chart</span>`}${banks.includes(l.code) ? ` <span class="pill grey">Bank</span>` : ""}</td>
      <td>${esc(l.description || "")}</td><td class="num">${l.dr ? money(l.dr) : ""}</td><td class="num">${l.cr ? money(l.cr) : ""}</td></tr>`).join("")}
    <tr class="sql-lines-total"><td colspan="2">Total</td><td class="num">${money(v.totals.dr)}</td><td class="num">${money(v.totals.cr)}</td></tr></tbody></table></div>`;
}

// Where a version came from: the report or paste it was read from, and when.
const ledgerSource = v => {
  const b = v.batch || {}, from = { journal: "SQL's GL Journal of Transaction", grid: "the journal lines pasted", legacy: "the journal lines pasted before" }[b.report] || "SQL";
  return `Version ${v.version}, ${esc(fmtDate(v.doc_date))}, from ${from}${b.file_name ? ` (${esc(b.file_name)})` : ""}${b.read_at ? `, read ${esc(b.read_at.replace("T", " "))}` : ""}`;
};

// The inline row a lines pill opens: the current version's lines, the checks on them, and the earlier versions.
function ledgerDocView(v) {
  const [cur, ...older] = v.versions;
  const state = cur.state === "gone" ? ` <span class="pill bad">No longer in SQL</span>` : cur.state === "superseded" ? ` <span class="pill grey">Replaced</span>` : "";
  return `<div class="sql-doc">
    <div class="row spread"><b>${esc(v.doc_no)}${cur.book_label ? ` <span class="muted">· ${esc(cur.book_label)}</span>` : ""}${state}</b><span class="note">${ledgerSource(cur)}</span></div>
    ${ledgerLinesTable(cur, v.bank_codes || [])}
    ${v.checks.length ? v.checks.map(c => `<div class="note warn-text">${esc(c)}</div>`).join("") : `<div class="note">The lines balance and agree with the listing.</div>`}
    ${older.length ? `<details><summary class="note">Earlier versions (${older.length})</summary>${older.map(o => `<div class="note">${ledgerSource(o)}</div>${ledgerLinesTable(o, v.bank_codes || [])}`).join("")}</details>` : ""}
  </div>`;
}

// The card of what SQL's own reports said when they were last read: the journal's counts, and the ledger's and trial
// balance's differences from the account lines, with the checks that couldn't run and why.
function sqlChecksCard(d) {
  const reads = d.ledger?.reads || {}, orph = d.ledger?.orphans || { no_listing: [], own_lines: [], not_in_journal: [], before_tracking: 0 };
  if (!Object.keys(reads).length && !orph.no_listing.length && !(orph.own_lines || []).length && !orph.not_in_journal.length) return "";
  const head = (kind, b) => `<div class="row spread"><h3>${GL_KIND[kind]}</h3><span class="muted">${esc(b.file_name || "")}${b.period_from ? ` · ${shortDate(b.period_from)} to ${shortDate(b.period_to)}` : b.period_to ? ` · as at ${shortDate(b.period_to)}` : ""} · read ${esc((b.read_at || "").replace("T", " "))}</span></div>`;
  const journal = b => {
    const s = b.summary || {};
    return `${head("journal", b)}<div class="note">${plural(s.docs || 0, "document")} (${s.new || 0} new, ${s.changed || 0} changed, ${s.same || 0} unchanged${s.back ? `, ${s.back} back in SQL` : ""}, ${s.gone || 0} no longer in SQL), ${plural(s.lines || 0, "line")}.</div>
      ${s.note ? `<div class="note">${esc(s.note)}</div>` : ""}
      ${s.reused?.length ? `<div class="note warn-text">Moved by more than 180 days, so the number may have been used again in SQL: ${esc(s.reused.join(", "))}.</div>` : ""}
      ${(s.recon_changed || []).map(m => `<div class="note warn-text">The bank reconciliation of ${esc(monthName(m.month))}, signed off, changed: money in ${money(m.before.in)} → ${money(m.after?.in)}, money out ${money(m.before.out)} → ${money(m.after?.out)}. It stays signed off; check it again.</div>`).join("")}`;
  };
  const report = (kind, b) => {
    const rs = b.results || [], warns = rs.filter(r => r.outcome === "warn");
    return `${head(kind, b)}
      ${warns.length ? `<div class="tbl-wrap"><table><thead><tr><th>Account</th><th>What differs</th><th class="num">SQL's figure</th><th class="num">The lines</th><th class="num">Difference</th></tr></thead><tbody>
        ${warns.map(r => `<tr><td class="mono">${esc(r.subject || "")}</td><td>${esc(r.text)}</td><td class="num">${money(sen(r.expected_sen))}</td><td class="num">${money(sen(r.actual_sen))}</td>
          <td class="num">${r.expected_sen != null && r.actual_sen != null ? money(sen(r.actual_sen - r.expected_sen)) : "—"}</td></tr>`).join("")}</tbody></table></div>`
        : `<div class="note"><span class="pill ok">No differences</span></div>`}
      ${kind === "trial_balance" && b.stale && warns.length ? `<div class="banner grey"><b>Possibly out of date</b><span>A GL Journal of Transaction read after this trial balance changed documents in its dates, so these differences may only be the trial balance being old. Export SQL's Trial Balance again for the same dates (${b.period_from ? `${shortDate(b.period_from)} to ` : "as at "}${shortDate(b.period_to)}) and Fetch it.</span></div>` : ""}
      ${rs.filter(r => r.outcome === "ok").map(r => `<div class="note">${esc(r.text)}</div>`).join("")}
      ${rs.filter(r => r.outcome === "skipped").map(r => `<div class="note">Not checked: ${esc(r.text)}</div>`).join("")}
      ${rs.filter(r => r.outcome === "info").map(r => `<div class="note">${esc(r.text)}</div>`).join("")}`;
  };
  return `<div class="card"><h2>Checks against SQL's reports</h2>
    <div class="note">The latest of SQL's GL Journal of Transaction, GL Ledger and Trial Balance fetched, checked against the account lines kept. Not checked: Period To Date and opening balances against the lines (SQL's trial balance moves earlier profit and loss into retained earnings on its From date), and anything after the dates the journals read cover.</div>
    ${reads.journal ? journal(reads.journal) : ""}
    ${["gl_ledger", "trial_balance"].filter(k => reads[k]).map(k => report(k, reads[k])).join("")}
    ${orph.no_listing.length ? `<h3>In SQL's journal but no listing fetched · ${orph.no_listing.length}</h3>
      <div class="note">Fetch SQL's listing these are in on the SQL import page, so each can be matched to a payment.</div>
      <div class="tbl-wrap"><table><thead><tr><th>Doc No</th><th>Date</th><th>Section</th><th></th></tr></thead><tbody>
      ${orph.no_listing.map(x => `<tr><td class="mono">${esc(x.doc_no)}</td><td>${shortDate(x.doc_date)}</td><td>${esc(x.book)}</td><td><button type="button" class="ghost small" data-sql-lines="${esc(x.doc_no)}">Lines</button></td></tr>`).join("")}</tbody></table></div>` : ""}
    ${(orph.own_lines || []).length ? `<details><summary><h3 style="display:inline">No listing this app reads yet · ${orph.own_lines.length}</h3></summary>
      <div class="note">No listing this app reads yet: checked by their account lines and SQL's trial balance. These are in other sections of SQL's journal (cash sales, credit or debit notes, deposits, refunds, contra and the like), so nothing asks for their listing.</div>
      <div class="tbl-wrap"><table><thead><tr><th>Doc No</th><th>Date</th><th></th></tr></thead><tbody>
      ${orph.own_lines.map(x => `<tr><td class="mono">${esc(x.doc_no)}</td><td>${shortDate(x.doc_date)}</td><td><button type="button" class="ghost small" data-sql-lines="${esc(x.doc_no)}">Lines</button></td></tr>`).join("")}</tbody></table></div></details>` : ""}
    ${orph.not_in_journal.length ? `<h3>Listing entries missing from SQL's Journal of Transaction · ${orph.not_in_journal.length}</h3>
      <div class="note">Dated inside a journal read, but not in it: deleted or renumbered in SQL. If SQL no longer has one, click Deleted in SQL: it is kept here, listed under Ignored, and left out of the checks (Un-ignore puts it back).</div>
      <div class="tbl-wrap"><table><thead><tr><th>Doc No</th><th>Date</th><th class="num">Amount</th><th></th></tr></thead><tbody>
      ${orph.not_in_journal.map(x => `<tr><td class="mono">${esc(x.doc_no)}</td><td>${shortDate(x.doc_date)}${x.gone ? ` <span class="pill bad">No longer in SQL</span>` : ""}</td><td class="num">${money(x.amount)}</td><td>${x.can_confirm ? `<button class="ghost small" data-sql-deleted-ids="${esc(x.ids.join(","))}">Deleted in SQL</button>` : `<span class="muted">Linked to a payment: unlink it first</span>`}</td></tr>`).join("")}</tbody></table></div>` : ""}
    ${orph.before_tracking ? `<div class="note muted">${plural(orph.before_tracking, "document")} before the first month tracked ${orph.before_tracking === 1 ? "has" : "have"} no listing or ${orph.before_tracking === 1 ? "is" : "are"} missing from the journal; months before tracking aren't checked.</div>` : ""}
  </div>`;
}

// The fetch preview's "Account lines" box: what keeping SQL's journal would do to the documents kept, and the journals
// that start counting in the bank reconciliation (a signed-off month named).
function sqlLedgerBox(l) {
  if (!l) return "";
  const t = l.totals, c = l.counting || { journals: [], signed_off: [] };
  return `<div class="sql-fetch"><b>Account lines</b>
    ${l.refused ? `<div class="note warn-text">${esc(l.refused)}</div>` : ""}
    ${t.docs ? `<div>${plural(t.docs, "document")}, ${plural(t.lines, "line")}: <b>${t.new} new</b>, ${t.changed} changed, ${t.same} unchanged${t.back ? `, ${t.back} back in SQL` : ""}, ${t.gone} no longer in SQL.</div>` : ""}
    ${l.files.map(f => `<div class="row spread"><span>${esc(f.name)} <span class="muted">· ${esc(f.title)}, ${esc(f.period)}</span></span><span class="muted">${f.kind === "journal" ? `${plural(f.docs, "document")}, ${plural(f.lines, "line")}` : esc(f.note)}</span></div>
      ${f.kind === "journal" && f.note ? `<div class="note">${esc(f.note)}</div>` : ""}`).join("")}
    ${l.gone.length ? `<div class="note"><b>No longer in SQL</b> (deleted or renumbered there; kept here, marked): ${l.gone.map(x => `${esc(x.doc_no)} (${shortDate(x.doc_date)}${x.payment ? `, linked to ${esc(x.payment)}` : ""}${x.bank_move ? `, moved ${money(Math.abs(x.bank_move))} on the bank` : ""}${x.signed_off ? ` <span class="pill warn">${esc(monthName(x.month))} signed off</span>` : ""})`).join("; ")}.</div>` : ""}
    ${c.journals.length ? `<div class="sql-warn"><b>${plural(c.journals.length, "journal")} will count in the bank reconciliation</b> (lines on ${esc(c.bank_code)}):
      ${c.journals.map(j => `<div class="note">${esc(j.doc_no)}, ${shortDate(j.doc_date)}: ${money(Math.abs(j.amount))} ${j.amount > 0 ? "into" : "out of"} the bank${j.before != null ? ` (counted as ${money(j.before)} until now)` : ""}${j.listed ? "" : ", once its listing is imported"}${j.signed_off ? ` <span class="pill warn">${esc(monthName(j.month))} signed off</span>` : ""}</div>`).join("")}</div>` : ""}
    ${c.signed_off.length ? `<div class="note warn-text">The book figures of ${c.signed_off.map(m => esc(monthName(m))).join(", ")} will change. Nothing is un-signed: check those months again after importing.</div>` : ""}
  </div>`;
}

async function viewSql(main) {
  const e = ent();
  if (!e.uses_sql) {
    main.innerHTML = `${entityPicker()}<div class="card"><h1>SQL import</h1><div class="note">${esc(e.name)} isn't kept in SQL Account, so there's nothing to import.</div></div>`;
    return;
  }
  const d = await api(`/api/sql/entries?entity=${state.entity}`);
  state.miData = d.myinvois;
  state.invPrint = d.invoice_print;
  const candOpts = u => `<option value="">Choose a payment…</option>${paymentOptions(d.candidates, u)}`;
  const unlinkBtn = x => `<button class="ghost small" data-sql-unlink="${x.id}">Unlink</button>`;
  const unRow = u => `<tr><td class="mono">${esc(u.doc_no)}</td><td>${shortDate(u.doc_date)}</td><td>${esc(u.description)}${u.payee ? `<div class="note">${esc(u.payee)}</div>` : ""}${sqlCodes(u)}${linesPill(d.lines, u)}
        ${u.direction === "in" ? `<span class="pill">Money in</span>` : ""}${u.einvoice ? ` <span class="pill ok">e-Invoice ${esc(u.einvoice.slice(0, 8))}…</span>` : ""}${changedInSql(u)}</td>
        <td class="num">${money(u.amount)}</td>
        <td><div class="row" style="flex-wrap:nowrap;gap:6px"><select data-sql-link="${u.id}" style="max-width:240px">${candOpts(u)}</select><button class="ghost small" data-sql-link-go="${u.id}">Link</button></div></td>
        <td><div class="row"><button class="ghost small" data-sql-create="${u.id}">Create payment</button><button class="ghost small" data-sql-ignore="${u.id}">Ignore</button></div></td></tr>`;
  // A voucher changed in SQL whose earlier entry is linked: shown once, under Changed in SQL, until the owner moves the link.
  const changedIds = new Set((d.changed || []).map(x => x.new.id));
  const waiting = d.unlinked.filter(u => !u.correction && !changedIds.has(u.id)), corrections = d.unlinked.filter(u => u.correction && !changedIds.has(u.id));
  const changedCard = (d.changed || []).length ? `<div class="card"><h2>Changed in SQL</h2>
      <div class="note">These vouchers were edited in SQL after they were linked to a payment: the latest fetch gives another amount or date. The link stays on the earlier entry until you move it. Moving it keeps the earlier entry, marked as replaced.</div>
      ${d.changed.map(x => `<div class="sql-changed" data-sql-changed="${x.old.id}" style="padding:8px 0;border-top:1px solid var(--line)">
        <div><b class="mono">${esc(x.doc_no)}</b> changed in SQL ${esc(x.words)}.</div>
        <div class="note">Linked to ${esc(x.payment.description)}${x.payment.month_label ? ` (${esc(x.payment.month_label)})` : ""}, whose amount is ${money(x.payment.amount)}.${x.ledger ? (x.ledger.agrees ? ` SQL's GL Journal of Transaction (version ${x.ledger.version}) already has ${money(x.ledger.total)}.` : ` SQL's GL Journal of Transaction kept here still has ${money(x.ledger.total)}: fetch it again for the same dates so the account lines follow.`) : ""}</div>
        ${x.amount_follows ? `<label class="row" style="gap:6px"><input type="checkbox" data-sql-follow="1"> Also change the payment's amount from ${money(x.old.amount)} to ${money(x.new.amount)}</label>` : ""}
        <div class="row"><button class="ghost small" type="button" data-sql-move="${x.old.id}" data-sql-move-to="${x.new.id}">Move the link to the new amount</button></div></div>`).join("")}</div>` : "";
  const replaced = d.superseded || [];
  const replacedCard = replaced.length ? `<div class="card"><details data-sql-open="replaced" ${state.sqlOpen.replaced ? "open" : ""}><summary><h2 style="display:inline">Replaced by a later version from SQL</h2> <span class="muted">· ${replaced.length}</span></summary>
      <div class="note">Earlier entries of vouchers edited in SQL. They are kept as they were read; the later entry is the one that counts.</div>
      <div class="tbl-wrap"><table><thead><tr><th>Doc No</th><th>Date</th><th>Description</th><th class="num">Amount then</th><th class="num">Amount now</th></tr></thead><tbody>
      ${replaced.map(x => `<tr><td class="mono">${esc(x.doc_no)}</td><td>${shortDate(x.doc_date)}${x.new_date !== x.doc_date ? `<div class="note">now ${shortDate(x.new_date)}</div>` : ""}</td><td>${esc(x.description)}</td><td class="num">${money(x.amount)}</td><td class="num">${money(x.new_amount)}</td></tr>`).join("")}
      </tbody></table></div></details></div>` : "";
  // Entries of months before the first month tracked: kept in the books mirror, listed read-only, never asked about.
  const before = d.before_tracking || [];
  state.sqlCorrections = corrections.map(u => u.id);
  const sqlText = x => [x.doc_no, fmtDate(x.doc_date), x.doc_date, x.description, x.payee, x.code, x.cheque_no, x.payment_method, LT.amount(x.amount), x.direction === "in" ? "money in" : "", x.payment_desc,
    x.payment_month ? monthName(x.payment_month) : "", x.einvoice ? "e-invoice" : ""].join(" ");
  const th = (cols, last) => `<thead><tr>${sortTh("sql", "doc", "Doc No")}${sortTh("sql", "date", "Date")}${sortTh("sql", "desc", "Description")}${sortTh("sql", "amount", "Amount", "num")}${cols}${last}</tr></thead>`;
  const none = (list, text) => `<tr><td colspan="6" class="empty">${list.length ? "No entry matches." : text}</td></tr>`;
  const entries = () => {
    const w = listRows("sql", waiting, sqlText), c = listRows("sql", corrections, sqlText), lk = listRows("sql", d.linked, sqlText), ig = listRows("sql", d.ignored, sqlText),
      bf = listRows("sql", before, sqlText);
    setCount("sql", w.length + c.length + lk.length + ig.length + bf.length, waiting.length + corrections.length + d.linked.length + d.ignored.length + before.length);
    return `${changedCard}<div class="card"><h2>SQL entries not linked to a payment</h2>
      <div class="row spread"><div class="note">These are in SQL but not in this tracker. Link each one to a payment, create a payment for it, or ignore it (e.g. a reversal).</div>
      ${waiting.length > 1 ? `<button class="ghost small" id="sqlCreateAll">Create payments for all ${waiting.length}</button>` : ""}</div>
      <div class="tbl-wrap"><table>${th(`<th>Link to</th>`, `<th></th>`)}<tbody>
      ${w.map(unRow).join("") || none(waiting, "Nothing waiting.")}
      </tbody></table></div>
      ${corrections.length ? `<div class="row spread"><div><h3>Probably a correction (no money moved)</h3>
        <div class="note">Reversals and contras made in SQL, or a receipt and a payment for the same amount on the same day. Create payments for all leaves these out. Ignore them, unless money really moved.</div></div>
        <button class="ghost small" id="sqlIgnoreAll">Ignore all ${corrections.length}</button></div>
      <div class="tbl-wrap"><table>${th(`<th>Link to</th>`, `<th></th>`)}<tbody>
      ${c.map(unRow).join("") || none(corrections, "")}</tbody></table></div>` : ""}</div>
    <div class="card"><details data-sql-open="linked" ${state.sqlOpen.linked ? "open" : ""}><summary><h2 style="display:inline">Linked to payments</h2> <span class="muted">· ${d.linked.length}</span></summary>
      <div class="note">Linked to the wrong payment? Unlink it: it goes back to the list above, and the payment's amount and paid date go back to what they were. A payment made from the voucher with Create payment, with nothing added since, is removed.</div>
      <div class="tbl-wrap"><table>${th(sortTh("sql", "pay", "Payment"), `<th></th>`)}<tbody>
      ${lk.map(x => `<tr><td class="mono">${esc(x.doc_no)}</td><td>${shortDate(x.doc_date)}</td><td>${esc(x.description)}${x.payee ? `<div class="note">${esc(x.payee)}</div>` : ""}${sqlCodes(x)}${linesPill(d.lines, x)}</td>
        <td class="num">${x.direction === "in" ? "+" : ""}${money(x.amount)}</td><td>${esc(x.payment_desc)} <span class="muted">(${monthName(x.payment_month)})</span></td>
        <td>${unlinkBtn(x)}</td></tr>`).join("") || none(d.linked, "None yet.")}
      </tbody></table></div></details></div>
    ${d.ignored.length ? `<div class="card"><details data-sql-open="ignored" ${state.sqlOpen.ignored ? "open" : ""}><summary><h2 style="display:inline">Ignored</h2> <span class="muted">· ${d.ignored.length}</span></summary>
      <div class="tbl-wrap"><table>${th("", `<th></th>`).replace("<th></th></tr>", "<th></th></tr>")}<tbody>
      ${ig.map(x => `<tr><td class="mono">${esc(x.doc_no)}</td><td>${shortDate(x.doc_date)}</td><td>${esc(x.description)}${x.payee ? `<div class="note">${esc(x.payee)}</div>` : ""}${sqlCodes(x)}${linesPill(d.lines, x)}</td>
        <td class="num">${x.direction === "in" ? "+" : ""}${money(x.amount)}</td><td><button class="ghost small" data-sql-unignore="${x.id}">Un-ignore</button></td></tr>`).join("") || none(d.ignored, "")}
      </tbody></table></div></details></div>` : ""}
    ${before.length ? `<div class="card"><details data-sql-open="before" ${state.sqlOpen.before ? "open" : ""}><summary><h2 style="display:inline">Before tracking (${before.length})</h2></summary>
      <div class="note">These SQL entries are from months before ${d.first_month ? esc(monthName(d.first_month)) : "the first month tracked"}, the first month tracked here. They are kept with SQL's books (their account lines and the checks against SQL's reports) but are not tracked as payments, so nothing asks you to link them.</div>
      <div class="tbl-wrap"><table>${th("", "")}<tbody>
      ${bf.map(x => `<tr><td class="mono">${esc(x.doc_no)}</td><td>${shortDate(x.doc_date)}</td><td>${esc(x.description)}${x.payee ? `<div class="note">${esc(x.payee)}</div>` : ""}${sqlCodes(x)}${linesPill(d.lines, x)}</td>
        <td class="num">${x.direction === "in" ? "+" : ""}${money(x.amount)}</td></tr>`).join("") || `<tr><td colspan="4" class="empty">No entry matches.</td></tr>`}
      </tbody></table></div></details></div>` : ""}${replacedCard}`;
  };
  main.innerHTML = `${entityPicker()}
    <div class="card"><h1>SQL import · ${esc(e.code)}</h1>
      <div class="note">Fetch (or paste) each SQL listing for the month: <b>Cash Book</b>, <b>Receipt Voucher</b>, <b>Payment Voucher</b>, <b>Journal</b> and <b>Customer Invoice</b>. Payments and receipts are matched to this tracker; customer invoices are filed against their checklist item of their own month (the e-Invoices for the fund received and the office rental) and linked to the money in they are for (the tenant's rent), and a payroll journal, if there is one, against Salary PVs in SQL. A document that appears in two listings is only kept once, so overlap is fine.</div>
      <div class="row spread" style="align-items:flex-start;gap:16px"><div><h3>Fetch exported listings (one click)</h3>
          <div class="note">Reads every SQL listing saved in <b>${esc(state.meta.sql_exports_dir)}</b>, whatever the files are called, and shows what is new and what is already imported. In SQL: open the listing, then the arrow beside the print button, <b>Export to Microsoft Excel Workbook</b>, and save it in <b>SQL Drive on SQL Connect › Download</b>. It reads the Cash Book, Payment Voucher, Official Receipt, Journal Voucher, Customer Invoice, Sales Invoice and Customer Payment listings (not their GST layouts). It also reads SQL's <b>GL Journal of Transaction</b> (the account lines of every document), <b>GL Ledger</b> (Local - Ledger - Detail, Level 1) and <b>Trial Balance</b> (This Month vs This Year with Opening): export them for the same dates as the listings, and the lines are kept and checked against SQL's own figures. It also reads a copy of SQL's <b>MyInvois Transaction</b> screen: click its grid, press <b>Ctrl+A</b> then <b>Ctrl+C</b>, paste it into a new Excel workbook with its headings and save it in the same folder under any name.</div>
          <details class="sql-folder"><summary>Use another folder</summary>
            <div class="row" style="align-items:flex-end"><label class="field" style="flex:1"><span>Folder the exports are saved in (leave empty for your Downloads folder)</span><input id="sqlDir" value="${state.meta.sql_exports_default ? "" : esc(state.meta.sql_exports_dir)}" placeholder="${esc(state.meta.sql_exports_dir)}" autocomplete="off"></label>
            <button class="ghost" id="sqlDirSave" type="button">Save folder</button></div></details></div>
        <button class="btn" id="sqlFetch" type="button" style="white-space:nowrap">Fetch from SQL exports</button></div>
      <div class="grid2">
        <form id="sqlPasteForm" style="display:grid;gap:8px"><h3>Copy and paste</h3>
          <div class="note">In SQL, open the Cash Book Listing, click any row, press <b>Ctrl+A</b> then <b>Ctrl+C</b>. Click in the box below and press <b>Ctrl+V</b>.</div>
          <textarea id="sqlPaste" rows="5" placeholder="Paste the SQL rows here" style="font-family:var(--f-mono);font-size:.8rem;border:1px solid var(--line-strong);background:var(--bg);border-radius:6px;padding:6px 8px"></textarea>
          <div class="row"><button class="btn" type="submit">Read pasted rows</button></div></form>
        <form id="sqlForm" style="display:grid;gap:8px;align-content:start"><h3>Or choose an exported file</h3>
          <label class="field"><span>SQL export (.xlsx, .xls, .csv)</span><input id="sqlFile" type="file" accept=".xlsx,.xls,.csv,.ods,.txt"></label>
          <div class="row"><button class="btn" type="submit">Read file</button></div></form>
      </div></div>
    <div id="sqlPreview"></div>
    <div class="card"><h2>Find an SQL entry</h2>${listBar("sql", "SQL entries")}</div>
    <div id="sqlEntries">${entries()}</div>
    <div class="card"><h2>Journals and invoices</h2>
      <div id="invPrint">${invoicePrintBar(d.invoice_print)}</div>
      <div class="tbl-wrap"><table><thead><tr><th>Doc No</th><th>Date</th><th>Description</th><th class="num">Amount</th><th>e-Invoice</th><th>Checklist item</th></tr></thead><tbody>
      ${d.documents.map(x => `<tr><td class="mono">${esc(x.doc_no)}</td><td>${shortDate(x.doc_date)}</td><td>${esc(x.description)}${x.payee ? `<div class="note">${esc(x.payee)}</div>` : ""}${sqlCodes(x)}${linesPill(d.lines, x)}</td>
        <td class="num">${money(x.amount)}</td><td>${einvPill(x)}${invoiceBtn(x)}</td>
        <td>${x.task_title ? `<span class="pill ok">${esc(x.task_title.split(":")[0])} (${esc(x.task_month)})</span>` : x.before_tracking ? `<span class="pill grey">Before tracking</span>` : `<span class="muted">—</span>`}
          ${x.kind === "journal" && x.bank_move != null ? `<div class="note">Moves ${money(Math.abs(x.bank_move))} ${x.bank_move > 0 ? "into" : "out of"} the bank, so it counts in the bank reconciliation.</div>` : ""}
          ${x.payment_id ? `<div class="row" style="gap:6px"><span class="note">${x.kind === "journal" ? "Payment" : "Receipt"}: ${esc(x.payment_desc)}</span>${unlinkBtn(x)}</div>`
            : x.kind === "journal" && x.bank_move != null && !x.before_tracking ? `<div class="row" style="flex-wrap:nowrap;gap:6px"><select data-sql-link="${x.id}" style="max-width:240px">${candOpts({ doc_no: x.doc_no, direction: x.bank_move > 0 ? "in" : "out" })}</select><button class="ghost small" data-sql-link-go="${x.id}">Link</button><button class="ghost small" data-sql-create="${x.id}">Create payment</button></div>` : ""}</td></tr>`).join("") || `<tr><td colspan="6" class="empty">Fetch SQL's Journal Voucher and Customer Invoice listings on this page to see them here.</td></tr>`}
      </tbody></table></div></div>
    ${sqlChecksCard(d)}
    <div class="card"><h2>e-Invoices</h2><div class="note">Every SQL document with an e-Invoice, and whether LHDN has validated it. Where a copy of SQL's MyInvois Transaction screen was read, what MyInvois says is shown beside it.</div>
      <div class="tbl-wrap"><table><thead><tr><th>Doc No</th><th>Date</th><th>Description</th><th class="num">Amount</th><th>Status</th><th>MyInvois</th><th></th></tr></thead><tbody>
      ${d.einvoices.map(x => `<tr><td class="mono">${esc(x.doc_no)}</td><td>${shortDate(x.doc_date)}</td><td>${esc(x.payee || x.description)}</td><td class="num">${money(x.amount)}</td><td>${einvPill(x)}</td>
        <td>${x.myinvois ? `<span class="mono">${esc(x.myinvois.uuid)}</span><div class="note">${esc(x.myinvois.type || "")} · ${esc(x.myinvois.status)}${x.myinvois.validated_at ? ` · validated ${esc(x.myinvois.validated_at)}` : ""}</div>` : `<span class="muted">—</span>`}</td>
        <td><div class="row" style="gap:6px">${x.payment_id ? unlinkBtn(x) : ""}${invoiceBtn(x)}</div></td></tr>`).join("") || `<tr><td colspan="7" class="empty">None imported yet.</td></tr>`}
      </tbody></table></div>
      <div id="miBox">${myinvoisBox(d.myinvois)}</div></div>
    <div class="card"><h2>Imported files</h2>${d.imports.map(i => `<div class="row spread"><span>${esc(i.filename)} <span class="muted">· ${i.entries} entries, ${i.linked} linked${i.lines ? ` · ${plural(i.lines, "line")}` : ""}</span></span><span class="muted">${esc(i.imported_at.replace("T", " "))}</span></div>`).join("") || `<div class="note">None yet.</div>`}</div>`;
  // A listing read but not imported yet stays, with links picked by hand, while you tidy the entries below.
  $("#sqlPaste").value = state.sqlPaste[state.entity] || "";
  paintCount("sql"); LIST_REDRAW.sql = () => { $("#sqlEntries").innerHTML = entries(); paintCount("sql"); };
  if (state.sqlPreview?.entity_id === state.entity) renderSqlPreview(state.sqlPreview);
}

