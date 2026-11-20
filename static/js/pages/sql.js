"use strict";
/* ---------------- Accounting › SQL import (slice 5) ----------------
   For a company Kept in SQL Account (a Kept here company at this address gets the "isn't used" card, core/states.js).
   Built to design/canvas/Sql.dc.html (the top half: the three steps, Fetch and its folder, paste or choose a file with drag
   and drop, the result: reading, what the fetch found, the preview, nothing new, the journal lines, imported) and
   SqlBooks.dc.html (the lower half: Changed in SQL, the entry lists, Journals and invoices, the checks against SQL's
   reports, and the account lines a pill opens). The e-Invoices card stays as it was until it gets its own page (slice 6).
   What the page keeps while it is on one company: sqState(). The preview read but not imported yet: state.sqlPreview. */

const SQL_FIELD_LABELS = { doc_no: "Doc No", date: "Date", description: "Description", payee: "Payee / name", amount: "Amount", debit: "Debit", credit: "Credit",
  einvoice: "e-Invoice UUID", doc_type: "Doc type", einvoice_status: "e-Invoice status", einvoice_link: "e-Invoice link",
  code: "SQL code", payment_method: "Payment method", cheque_no: "Cheque no.", dockey: "Doc key", currency_code: "Currency" };
// What SQL also says of an entry, under its payee: "Code 400-A001 · Chq 12345 · Method Maybank" (only what it has).
const sqlCodes = x => {
  const bits = [x.code && `Code ${x.code}`, x.cheque_no && `Chq ${x.cheque_no}`, x.payment_method && `Method ${x.payment_method}`].filter(Boolean);
  return bits.length ? `<div class="note small">${esc(bits.join(" · "))}</div>` : "";
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
// The section of SQL's journal a document is in, in words (as ledger.BOOK_WORDS says it), never the raw key.
const SQL_BOOK_WORDS = { bank: "the Bank Journal", general: "the General Journal", sales: "the Sales Journal", purchase: "the Purchase Journal", other: "another section" };
const sqlBook = b => b ? SQL_BOOK_WORDS[b] || "another section" : "";
// An amount in a column headed "Amount (RM)": the figure alone.
const sqAmt = n => n == null ? "—" : Number(n).toLocaleString("en-MY", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const sqWhen = iso => { if (!iso) return ""; const s = String(iso); return `${fmtDate(s)}${s.length > 10 ? ", " + s.slice(11, 16) : ""}`; };
const sqCap = s => s ? s[0].toUpperCase() + s.slice(1) : "";
const sqMonth = m => m ? `${MONTHS[+m.slice(5, 7) - 1]} ${m.slice(0, 4)}` : "";
const sqWords = list => list.length > 1 ? `${list.slice(0, -1).join(", ")} and ${list[list.length - 1]}` : list.join("");
// A fetch's or a paste's name with its time in words: "SQL exports fetched 18 Nov 2026, 10:42" (a file keeps its own name).
function sqTitle(name) {
  const m = /^(SQL (?:exports|reports) fetched|SQL listing pasted) (\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})\.\w+$/.exec(name || "");
  return m ? `${m[1]} ${+m[4]} ${MONTHS[+m[3] - 1]} ${m[2]}, ${m[5]}:${m[6]}` : name || "";
}

// The pill beside an SQL entry that says what SQL's Journal of Transaction gave for it (d.lines[entry id]); clicking
// it opens the lines under the row. "No lines" only shows when a journal read covered the entry's date and book.
function linesPill(lines, x) {
  const l = lines?.[x.id];
  if (!l) return "";
  if (!l.n) return ` <span class="pill grey">No lines</span>`;
  const [cls, text] = l.state === "gone" ? ["bad", "No longer in SQL"] : !l.balanced ? ["bad", "Lines don't balance"]
    : l.total_ok === false ? ["warn", "Lines ≠ amount"] : l.version > 1 ? ["warn", `Changed in SQL (v${l.version})`]
    : [l.unknown?.length || l.warnings ? "warn" : "ok", plural(l.n, "line")];
  return ` <button type="button" class="pill ${cls} pill-btn" data-sql-lines="${esc(x.doc_no)}" aria-expanded="false" title="Show the account lines">${esc(text)}<span class="chev" aria-hidden="true">${icon("chevronRight")}</span></button>`;
}

// One version of a document's account lines as a table: the bank's lines marked, a code the chart and the customers
// and suppliers don't know marked "Not in chart".
function ledgerLinesTable(v, banks) {
  const known = l => l.name_from === "chart" || l.name_from === "party" || l.control;
  return `<div class="tbl-wrap"><table class="sql-lines"><thead><tr><th>Account</th><th>Description</th><th class="num">Debit</th><th class="num">Credit</th></tr></thead><tbody>
    ${v.lines.map(l => `<tr class="${banks.includes(l.code) ? "sql-bank-line" : ""}"><td><span class="mono">${esc(l.code)}</span> ${esc(l.name || "")}${known(l) ? "" : ` <span class="pill warn">Not in chart</span>`}${banks.includes(l.code) ? ` <span class="pill grey">Bank</span>` : ""}</td>
      <td>${esc(l.description || "")}</td><td class="num">${l.dr ? sqAmt(l.dr) : ""}</td><td class="num">${l.cr ? sqAmt(l.cr) : ""}</td></tr>`).join("")}
    <tr class="sql-lines-total"><td colspan="2">Total</td><td class="num">${sqAmt(v.totals.dr)}</td><td class="num">${sqAmt(v.totals.cr)}</td></tr></tbody></table></div>`;
}

// Where a version came from: the report or paste it was read from, and when.
const ledgerSource = v => {
  const b = v.batch || {}, from = { journal: "SQL's GL Journal of Transaction", grid: "the journal lines pasted", legacy: "the journal lines pasted before" }[b.report] || "SQL";
  return `Version ${v.version}, ${esc(fmtDate(v.doc_date))}, from ${from}${b.file_name ? ` (${esc(b.file_name)})` : ""}${b.read_at ? `, read ${esc(b.read_at.replace("T", " "))}` : ""}`;
};

// The inline row a lines pill opens: the current version's lines, the checks on them, and the earlier versions.
function ledgerDocView(v) {
  const [cur, ...older] = v.versions;
  const state_ = cur.state === "gone" ? ` <span class="pill bad">No longer in SQL</span>` : cur.state === "superseded" ? ` <span class="pill grey">Replaced</span>` : "";
  const book = cur.book_label || sqlBook(cur.book);
  return `<div class="sql-doc">
    <div class="sql-doc-h"><b class="mono">${esc(v.doc_no)}</b>${book ? `<span class="muted">· ${esc(book)}</span>` : ""}${state_}<span class="note small sql-doc-src">${ledgerSource(cur)}</span></div>
    ${desktopNote("SQL's account lines", "The account lines are a wide table: it scrolls sideways in its own frame.")}
    ${ledgerLinesTable(cur, v.bank_codes || [])}
    <div class="sql-doc-checks">${v.checks.length ? v.checks.map(c => `<div class="note warn">${icon("alert")}<span>${esc(c)}</span></div>`).join("")
      : `<div class="note ok">${icon("check")}<span>The lines balance and agree with the listing.</span></div>`}
    ${older.length ? `<details><summary>Earlier versions (${older.length})</summary>${older.map(o => `<div class="note small">${ledgerSource(o)}</div>${ledgerLinesTable(o, v.bank_codes || [])}`).join("")}</details>` : ""}</div>
  </div>`;
}

// A card's head: its glyph, title (focusable, for the links that bring it into view), count and note, and what it can do.
const sqHead = (id, glyph, tone, title, count, note, extra = "") => `<div class="sq-head"><span class="sq-ic ${tone}">${icon(glyph)}</span><div class="sq-grow">
    <h2 id="${id}" tabindex="-1">${title}${count != null ? ` <span class="sq-count">· ${count}</span>` : ""}</h2>${note ? `<span class="note">${note}</span>` : ""}</div>${extra}</div>`;
// A card that folds: its head is one button (aria-expanded); the body is drawn only when open.
function sqFold(key, glyph, tone, title, count, open, body, note = "") {
  return `<section class="card sq-card" id="sq-${key}" aria-labelledby="sq-fold-${key}-t">
    <h2 class="sq-fold-h"><button type="button" class="sq-fold" id="sq-fold-${key}" data-sq-fold="${key}" aria-expanded="${open}" aria-controls="sq-${key}-body">
      <span class="chev${open ? " on" : ""}" aria-hidden="true">${icon("chevronRight")}</span><span class="sq-ic ${tone}">${icon(glyph)}</span><span class="sq-fold-t" id="sq-fold-${key}-t">${title}</span>${count != null ? `<span class="muted">· ${count}</span>` : ""}</button></h2>
    ${open ? `<div class="sq-fold-body" id="sq-${key}-body">${note ? `<p class="sq-note">${note}</p>` : ""}${body}</div>` : ""}</section>`;
}
const sqNone = (glyph, tone, text) => `<div class="sq-none ${tone}">${icon(glyph)}<span>${esc(text)}</span></div>`;

// The card of what SQL's own reports said when they were last read: the journal's counts, and the ledger's and trial
// balance's differences from the account lines, with the checks that couldn't run and why; then SQL's documents that no
// listing matches, each with its section of SQL's journal in words.
function sqlChecksCard(d) {
  const reads = d.ledger?.reads || {}, orph = d.ledger?.orphans || { no_listing: [], own_lines: [], not_in_journal: [], before_tracking: 0 };
  if (!Object.keys(reads).length && !orph.no_listing.length && !(orph.own_lines || []).length && !orph.not_in_journal.length) return "";
  const head = (kind, b) => `<div class="sq-rep-h"><h3>${GL_KIND[kind]}</h3><span class="note">${esc(b.file_name || "")}${b.period_from ? ` · ${shortDate(b.period_from)} to ${shortDate(b.period_to)}` : b.period_to ? ` · as at ${shortDate(b.period_to)}` : ""} · read ${esc((b.read_at || "").replace("T", " "))}</span></div>`;
  const journal = b => {
    const s = b.summary || {};
    return `<div class="sq-rep">${head("journal", b)}<div class="note">${plural(s.docs || 0, "document")} (${s.new || 0} new, ${s.changed || 0} changed, ${s.same || 0} unchanged${s.back ? `, ${s.back} back in SQL` : ""}, ${s.gone || 0} no longer in SQL), ${plural(s.lines || 0, "line")}.</div>
      ${s.note ? `<div class="note">${esc(s.note)}</div>` : ""}
      ${s.reused?.length ? `<div class="note warn">Moved by more than 180 days, so the number may have been used again in SQL: ${esc(s.reused.join(", "))}.</div>` : ""}
      ${(s.recon_changed || []).map(m => `<div class="note warn">The bank reconciliation of ${esc(monthName(m.month))}, signed off, changed: money in ${money(m.before.in)} → ${money(m.after?.in)}, money out ${money(m.before.out)} → ${money(m.after?.out)}. It stays signed off; check it again.</div>`).join("")}</div>`;
  };
  const report = (kind, b) => {
    const rs = b.results || [], warns = rs.filter(r => r.outcome === "warn");
    return `<div class="sq-rep">${head(kind, b)}
      ${warns.length ? `<div class="tbl-wrap sq-frame"><table class="sq-tbl sq-diff"><thead><tr><th>Account</th><th>What differs</th><th class="num">SQL's figure</th><th class="num">The lines</th><th class="num">Difference</th></tr></thead><tbody>
        ${warns.map(r => `<tr><td class="mono">${esc(r.subject || "")}</td><td>${esc(r.text)}</td><td class="num">${sqAmt(sen(r.expected_sen))}</td><td class="num">${sqAmt(sen(r.actual_sen))}</td>
          <td class="num sq-bad">${r.expected_sen != null && r.actual_sen != null ? sqAmt(sen(r.actual_sen - r.expected_sen)) : "—"}</td></tr>`).join("")}</tbody></table></div>`
        : `<div><span class="pill ok">${icon("check")}No differences</span></div>`}
      ${kind === "trial_balance" && b.stale && warns.length ? `<div class="banner grey sq-stale" role="note">${icon("clock")}<b>Possibly out of date</b><span>A GL Journal of Transaction read after this trial balance changed documents in its dates, so these differences may only be the trial balance being old. Export SQL's Trial Balance again for the same dates (${b.period_from ? `${shortDate(b.period_from)} to ` : "as at "}${shortDate(b.period_to)}) and Fetch it.</span></div>` : ""}
      ${rs.filter(r => r.outcome === "ok").map(r => `<div class="note">${esc(r.text)}</div>`).join("")}
      ${rs.filter(r => r.outcome === "skipped").map(r => `<div class="note">Not checked: ${esc(r.text)}</div>`).join("")}
      ${rs.filter(r => r.outcome === "info").map(r => `<div class="note">${esc(r.text)}</div>`).join("")}</div>`;
  };
  const linesBtn = no => `<button type="button" class="ghost small sq-lines-b" data-sql-lines="${esc(no)}" aria-expanded="false" aria-label="Show the account lines of ${esc(no)}">Lines<span class="chev" aria-hidden="true">${icon("chevronRight")}</span></button>`;
  const ownOpen = !!state.sqlOpen.own, own = orph.own_lines || [];
  return `<section class="card sq-card" id="sql-checks" aria-labelledby="sql-checks-h">
    ${sqHead("sql-checks-h", "verified", "brand", "Checks against SQL's reports", null, "The latest of SQL's GL Journal of Transaction, GL Ledger and Trial Balance fetched, checked against the account lines kept. Not checked: Period To Date and opening balances against the lines (SQL's trial balance moves earlier profit and loss into retained earnings on its From date), and anything after the dates the journals read cover.")}
    ${desktopNote("The checks against SQL's reports", "The checks are wide tables: each scrolls sideways in its own frame.")}
    ${reads.journal ? journal(reads.journal) : ""}
    ${["gl_ledger", "trial_balance"].filter(k => reads[k]).map(k => report(k, reads[k])).join("")}
    ${orph.no_listing.length ? `<div class="sq-orph"><h3>In SQL's journal but no listing fetched · ${orph.no_listing.length}</h3>
      <p class="note">Fetch SQL's listing these are in on the SQL import page, so each can be matched to a payment.</p>
      <div class="tbl-wrap"><table class="sq-tbl sq-otbl"><thead><tr><th>Doc no.</th><th>Date</th><th>Section</th><th><span class="sr-only">Action</span></th></tr></thead><tbody>
      ${orph.no_listing.map(x => `<tr><td class="mono sq-no">${esc(x.doc_no)}</td><td class="nowrap">${shortDate(x.doc_date)}</td><td>${esc(sqlBook(x.book))}</td><td class="sq-act">${linesBtn(x.doc_no)}</td></tr>`).join("")}</tbody></table></div></div>` : ""}
    ${own.length ? `<div class="sq-orph"><h3 class="sq-fold-h"><button type="button" class="sq-fold small" id="sq-fold-own" data-sq-fold="own" aria-expanded="${ownOpen}" aria-controls="sq-own-body"><span class="chev${ownOpen ? " on" : ""}" aria-hidden="true">${icon("chevronRight")}</span>No listing this app reads yet · ${own.length}</button></h3>
      ${ownOpen ? `<div id="sq-own-body"><p class="note">No listing this app reads yet: checked by their account lines and SQL's trial balance. These are in other sections of SQL's journal (cash sales, credit or debit notes, deposits, refunds, contra and the like), so nothing asks for their listing.</p>
      <div class="tbl-wrap"><table class="sq-tbl sq-otbl"><thead><tr><th>Doc no.</th><th>Date</th><th><span class="sr-only">Action</span></th></tr></thead><tbody>
      ${own.map(x => `<tr><td class="mono sq-no">${esc(x.doc_no)}</td><td class="nowrap">${shortDate(x.doc_date)}</td><td class="sq-act">${linesBtn(x.doc_no)}</td></tr>`).join("")}</tbody></table></div></div>` : ""}</div>` : ""}
    ${orph.not_in_journal.length ? `<div class="sq-orph"><h3>Listing entries missing from SQL's Journal of Transaction · ${orph.not_in_journal.length}</h3>
      <p class="note">Dated inside a journal read, but not in it: deleted or renumbered in SQL. If SQL no longer has one, click Deleted in SQL: it is kept here, listed under Ignored, and left out of the checks (Un-ignore puts it back).</p>
      <div class="tbl-wrap"><table class="sq-tbl sq-otbl"><thead><tr><th>Doc no.</th><th>Date</th><th class="num">Amount (RM)</th><th><span class="sr-only">Action</span></th></tr></thead><tbody>
      ${orph.not_in_journal.map(x => `<tr><td class="mono sq-no">${esc(x.doc_no)}</td><td class="nowrap">${shortDate(x.doc_date)}${x.gone ? ` <span class="pill bad">No longer in SQL</span>` : ""}</td><td class="num">${sqAmt(x.amount)}</td><td class="sq-act">${x.can_confirm ? `<button type="button" class="ghost small" data-sql-deleted-ids="${esc(x.ids.join(","))}" aria-label="Deleted in SQL: ${esc(x.doc_no)}">Deleted in SQL</button>` : `<span class="muted">Linked to a payment: unlink it first</span>`}</td></tr>`).join("")}</tbody></table></div></div>` : ""}
    ${orph.before_tracking ? `<p class="note sq-pad">${plural(orph.before_tracking, "document")} before the first month tracked ${orph.before_tracking === 1 ? "has" : "have"} no listing or ${orph.before_tracking === 1 ? "is" : "are"} missing from the journal; months before tracking aren't checked.</p>` : ""}
  </section>`;
}

// The preview's "Account lines" box: what keeping SQL's journal would do to the documents kept, and the journals that
// start counting in the bank reconciliation (a signed-off month named).
function sqlLedgerBox(l) {
  if (!l) return "";
  const t = l.totals, c = l.counting || { journals: [], signed_off: [] };
  return `<div class="sq-lbox" role="group" aria-labelledby="sql-lines-h">
    <div class="sq-lbox-h">${icon("sheet")}<h3 id="sql-lines-h">Account lines</h3>${t.docs ? `<span class="note">${plural(t.docs, "document")}, ${plural(t.lines, "line")}: <b>${t.new} new</b>, ${t.changed} changed, ${t.same} unchanged${t.back ? `, ${t.back} back in SQL` : ""}, ${t.gone} no longer in SQL.</span>` : ""}</div>
    ${l.refused ? `<div class="sq-lbox-r note warn">${esc(l.refused)}</div>` : ""}
    ${l.files.map(f => `<div class="sq-lbox-r"><span class="sq-grow">${esc(f.name)} <span class="muted">· ${esc(f.title)}, ${esc(f.period)}</span></span><span class="muted">${f.kind === "journal" ? `${plural(f.docs, "document")}, ${plural(f.lines, "line")}` : esc(f.note)}</span></div>
      ${f.kind === "journal" && f.note ? `<div class="sq-lbox-r note">${esc(f.note)}</div>` : ""}`).join("")}
    ${l.gone.length ? `<div class="sq-lbox-r note"><b>No longer in SQL</b> (deleted or renumbered there; kept here, marked): ${l.gone.map(x => `${esc(x.doc_no)} (${shortDate(x.doc_date)}${x.payment ? `, linked to ${esc(x.payment)}` : ""}${x.bank_move ? `, moved ${money(Math.abs(x.bank_move))} on the bank` : ""}${x.signed_off ? ` <span class="pill warn">${esc(monthName(x.month))} signed off</span>` : ""})`).join("; ")}.</div>` : ""}
    ${c.journals.length ? `<div class="sq-lbox-warn">${icon("bank")}<div><b>${plural(c.journals.length, "journal")} will count in the bank reconciliation</b> (lines on ${esc(c.bank_code)}):
      ${c.journals.map(j => `<div>${esc(j.doc_no)}, ${shortDate(j.doc_date)}: ${money(Math.abs(j.amount))} ${j.amount > 0 ? "into" : "out of"} the bank${j.before != null ? ` (counted as ${money(j.before)} until now)` : ""}${j.listed ? "" : ", once its listing is imported"}${j.signed_off ? ` <span class="pill warn">${esc(monthName(j.month))} signed off</span>` : ""}</div>`).join("")}</div></div>` : ""}
    ${c.signed_off.length ? `<div class="sq-lbox-r note warn">The book figures of ${c.signed_off.map(m => esc(monthName(m))).join(", ")} will change. Nothing is un-signed: check those months again after importing.</div>` : ""}
  </div>`;
}

/* ---------------- What the page keeps ---------------- */
// One company at a time: how to bring in one listing (paste or file), the folder box, what is being read, the result
// of the last import, the boxes that ask before Create payments for all and Ignore all, the payments picked to link.
function sqState() {
  if (!state.sq || state.sq.entity !== state.entity)
    state.sq = { entity: state.entity, mode: "paste", folderEdit: false, folderVal: "", folderMsg: "", folderErr: "", fetchErr: "", pasteErr: "", fileErr: "",
      file: null, drag: false, reading: null, legend: false, left: false, cols: false, done: null, arrive: false, confirmAll: false, confirmIgnore: false, sel: {}, count: [0, 0] };
  return state.sq;
}
const sqPreviewNow = () => state.sqlPreview?.entity_id === state.entity ? state.sqlPreview : null;

/* ---------------- The top half: steps, Fetch, one listing, the result ---------------- */
function sqStepsHtml() {
  const done = !!sqState().done;
  return `<ol class="sq-steps">
    <li><span class="sq-n">1</span><div><b>Sign in to SQL Account</b><span class="note">You sign in yourself. HR Payments never signs in for you.</span></div></li>
    <li><span class="sq-n">2</span><div><b>Export each listing</b><span class="note">Open the listing, click the arrow beside the print button and choose Export to Microsoft Excel Workbook. Save it in SQL Drive, in the Download folder.</span></div></li>
    <li class="${done ? "done" : "now"}"><span class="sq-n">${done ? icon("check") : "3"}</span><div><b>${done ? "Imported" : "Fetch them here"}</b><span class="note">${done ? "Export again whenever SQL has something new. A document is never imported twice." : "Press Fetch from SQL exports, check the preview, then import."}</span></div></li></ol>`;
}

// Fetch: the cobalt button until there is a preview or a result to look at (then the secondary one, "Fetch again").
function sqFetchParts() {
  const S = sqState(), busy = S.reading === "fetch", p = sqPreviewNow();
  const primary = !p && !S.done && !S.folderEdit, again = !!(p?.fetch || S.done?.src === "fetch");
  return { busy, cls: `${primary ? "btn" : "ghost"} sq-fetch-b`,
    inner: `${busy ? `<span class="spin${primary ? "" : " sq-spin"}" aria-hidden="true"></span>` : icon("download")}${busy ? "Reading the folder…" : again ? "Fetch again" : "Fetch from SQL exports"}` };
}
function sqFetchBtn() {
  const f = sqFetchParts();
  return `<button type="button" class="${f.cls}" id="sqlFetch" aria-busy="${f.busy}"${f.busy ? ' aria-disabled="true"' : ""}>${f.inner}</button>`;
}
function sqFetchInner() {
  const S = sqState(), m = state.meta, dir = m.sql_exports_dir || "", def = !!m.sql_exports_default, busy = S.reading === "fetch";
  return `<div class="sq-fetch-top"><span class="sq-plate">${icon("folder")}</span>
      <div class="sq-grow"><h2 id="sq-fetch-h">Fetch exported listings (one click)</h2><span class="note">Reads every SQL listing saved in the folder, whatever the files are called, and shows what is new and what is already imported.</span></div>
      <div class="sq-fetch-go">${sqFetchBtn()}<span class="note small" id="sq-fetch-hint">${busy ? "Opening each workbook in the folder" : "Nothing in the folder is moved or changed"}</span></div></div>
    <div class="sq-folder">${icon("folder")}<span class="note">Reads</span><span class="mono sq-path">${esc(dir)}</span>${def ? `<span class="pill grey">Your Downloads folder</span>` : ""}
      ${S.folderMsg && !S.folderEdit ? `<span class="sq-saved" role="status">${icon("check")}${esc(S.folderMsg)}</span>` : ""}<span class="sq-fill"></span>
      <button type="button" class="ghost small" id="sq-folder-btn" data-sq-folder="1" aria-expanded="${S.folderEdit}" aria-controls="sq-folder-edit">${icon("edit")}Use another folder</button></div>
    ${S.folderEdit ? `<div class="sq-folder-edit" id="sq-folder-edit"><div class="sq-folder-row">
        <label class="field sq-grow"><span>Folder the exports are saved in (leave empty for your Downloads folder)</span><input id="sqlDir" value="${esc(S.folderVal)}" placeholder="${esc(dir)}" autocomplete="off" spellcheck="false" aria-describedby="sq-folder-help"${S.folderErr ? ' aria-invalid="true"' : ""}></label>
        <button type="button" class="ghost" data-sq-folder="1">Cancel</button><button type="button" class="btn" id="sqlDirSave">Save folder</button></div>
      ${S.folderErr ? `<span class="field-err" role="alert">${icon("alert")}${esc(S.folderErr)}</span>` : ""}
      <span class="note small" id="sq-folder-help">The full path, starting with the drive letter. Leave it empty to use your Downloads folder. Nothing in the folder is ever changed.</span></div>` : ""}
    ${S.fetchErr ? `<div class="sq-alert" role="alert">${icon("alert")}<div class="sq-grow"><b>The fetch couldn't read the folder</b><div class="note">${esc(S.fetchErr)} Nothing was imported.</div></div>
      <div class="sq-alert-go"><button type="button" class="ghost small" data-sq-folder-fix="1">Use another folder</button><button type="button" class="sq-linkbtn" data-sq-paste-instead="1">Paste a listing instead</button></div></div>` : ""}
    <p class="sq-howto">In SQL: open the listing, then the arrow beside the print button, <b>Export to Microsoft Excel Workbook</b>, and save it in <b>SQL Drive on SQL Connect › Download</b>. It reads the <b>Cash Book</b>, <b>Payment Voucher</b>, <b>Official Receipt</b>, <b>Journal Voucher</b>, <b>Customer Invoice</b>, <b>Sales Invoice</b>, <b>Customer Payment</b>, <b>Supplier Invoice</b> and <b>Supplier Payment</b> listings (not their GST layouts). It also reads SQL's <b>GL Journal of Transaction</b> (the account lines of every document), <b>GL Ledger</b> (Local - Ledger - Detail, Level 1) and <b>Trial Balance</b> (This Month vs This Year with Opening): export them for the same dates as the listings, and the lines are kept and checked against SQL's own figures. It also reads a copy of SQL's <b>MyInvois Transaction</b> screen: click its grid, press <b>Ctrl+A</b> then <b>Ctrl+C</b>, paste it into a new Excel workbook with its headings and save it in the same folder under any name.</p>`;
}

// One listing brought in by hand: two tabs, Copy and paste and Choose an exported file (the box also takes a dropped file).
const SQ_TYPES = /\.(xlsx|xls|csv|ods|txt)$/i, SQ_MAX = 25 * 1024 * 1024;
function sqFileHint() { const S = sqState(); return S.file ? `Chosen: ${S.file.name}` : ".xlsx, .xls, .csv, .ods or .txt, exported from SQL Account"; }
function sqFileErr() {
  const S = sqState();
  return S.fileErr ? `<div class="sq-ferr" role="alert"><span>${icon("alert")}${esc(S.fileErr)}</span>${/paste this listing instead\.?$/i.test(S.fileErr) ? `<button type="button" class="sq-linkbtn" data-sq-paste-instead="1">Paste this listing instead</button>` : ""}</div>` : "";
}
function sqBringInner() {
  const S = sqState(), paste = S.mode === "paste", busy = S.reading === "paste" || S.reading === "file";
  const tab = (k, glyph, label) => `<button type="button" role="tab" class="sq-tab" id="sql-tab-${k}" data-sq-tab="${k}" aria-selected="${S.mode === k}" aria-controls="sql-panel" tabindex="${S.mode === k ? 0 : -1}">${icon(glyph)}${label}</button>`;
  const btn = (id, label, reading) => `<button type="submit" class="ghost sq-read" id="${id}" aria-busy="${S.reading === reading}"${busy ? ' aria-disabled="true"' : ""}>${S.reading === reading ? `<span class="spin sq-spin" aria-hidden="true"></span>` : ""}${S.reading === reading ? (reading === "paste" ? "Reading the rows…" : "Reading the file…") : label}</button>`;
  return `<div class="sq-bring-top"><h2 class="sq-sub-h">Or bring in one listing yourself</h2>
      <div role="tablist" class="sq-tabs" aria-label="How to bring in one listing">${tab("paste", "clipboard", "Copy and paste")}${tab("file", "document", "Choose an exported file")}</div></div>
    <div id="sql-panel" role="tabpanel" aria-labelledby="sql-tab-${S.mode}">${paste
      ? `<form id="sqlPasteForm" class="sq-panel"><label class="sq-paste-l" for="sqlPaste">In SQL, open the listing, click any row, press <b>Ctrl+A</b> then <b>Ctrl+C</b>. Click in the box below and press <b>Ctrl+V</b>.</label>
          <textarea id="sqlPaste" rows="4" placeholder="Paste the SQL rows here" spellcheck="false"${S.pasteErr ? ' aria-invalid="true" aria-describedby="sq-paste-err"' : ""}></textarea>
          ${S.pasteErr ? `<span class="field-err" id="sq-paste-err" role="alert">${icon("alert")}${esc(S.pasteErr)}</span>` : ""}
          <div class="sq-panel-go">${btn("sq-read-paste", "Read pasted rows", "paste")}</div></form>`
      : `<form id="sqlForm" class="sq-panel"><label id="sql-drop" class="sq-drop${S.drag ? " on" : ""}${S.fileErr ? " bad" : ""}">${icon("upload")}
            <span class="sq-drop-t">${S.drag ? `<b>Drop the file to choose it</b>` : `<b>Choose an SQL export</b> or drop it here`}</span>
            <span class="note small" id="sql-file-hint">${esc(sqFileHint())}</span>
            <input id="sqlFile" class="sq-file-in" type="file" accept=".xlsx,.xls,.csv,.ods,.txt" aria-describedby="sql-file-hint"${S.fileErr ? ' aria-invalid="true"' : ""}></label>
          <div id="sq-ferr">${sqFileErr()}</div>
          <div class="sq-panel-go">${btn("sq-read-file", "Read file", "file")}</div></form>`}</div>`;
}

// What the fetch looked at (sqlfetch.py): seven statuses, each with one chip and one glyph; the reason says the rest.
const SQ_STATUS = {
  read: ["Read", "ok", "check", "A listing, a report of SQL's general ledger or a MyInvois copy this app reads. What is new is in the preview."],
  imported_before: ["Imported before", "grey", "history", "This exact file was imported earlier, so it is left alone."],
  copy: ["A copy", "grey", "copy", "The same file as another one in this fetch, so it is read once."],
  other_company: ["Another company", "warn", "company", "It is for a different company in Setup (a MyInvois copy is told by the TIN on its e-Invoices). Nothing was taken from it."],
  unknown_company: ["Company not in Setup", "warn", "company", "The company printed on it matches no company's name or registration number in Setup (a MyInvois copy: no company's TIN). If it is this company's, Take it for says so, once."],
  too_large: ["Too large", "bad", "alert", "An SQL export over 25 MB is not opened. Export a shorter period."],
  unreadable: ["Couldn't be read", "bad", "alert", "The file is locked, is in another currency, is a listing this app does not read yet, or does not add up. The reason says which."],
};
function sqFiles(f) {
  const read = f.files.filter(x => x.status === "read"), before = f.files.filter(x => x.status === "imported_before"),
    copies = f.files.filter(x => x.status === "copy"), unused = f.files.filter(x => !["read", "imported_before", "copy"].includes(x.status));
  return { read, before, copies, unused };
}
const sqSpan = x => x.period?.[0] ? `, ${shortDate(x.period[0])} to ${shortDate(x.period[1])}` : x.period?.[1] ? `, as at ${shortDate(x.period[1])}` : "";
function sqUnusedHtml(unused) {
  if (!unused.length) return "";
  return `<div class="sq-un-h">${icon("alert")}<h3>${plural(unused.length, "file")} not used</h3><span class="note">Each says why. Nothing was taken from them.</span></div>`
    + unused.map((x, i) => {
      const [word, tone, glyph] = SQ_STATUS[x.status] || SQ_STATUS.unreadable, id = `sq-un-${i}`, reason = sqCap(x.reason || "");
      const act = x.take_for ? `<button type="button" class="ghost small sq-take" data-sql-take="${esc(x.company)}" aria-describedby="${id}">Take it for ${esc(x.take_for)}</button>`
        : /paste this listing instead\.?$/i.test(reason) ? `<button type="button" class="sq-linkbtn" data-sq-paste-instead="1">Paste this listing instead</button>`
        : /Setup › Companies/.test(reason) ? `<button type="button" class="sq-linkbtn" data-inv-setup="1">Open Setup › Companies</button>`
        : /then fetch again\.?$/i.test(reason) ? `<button type="button" class="ghost small" data-sq-refetch="1">Fetch again</button>` : "";
      return `<div class="sq-file"><span class="sq-fi ${tone}">${icon(tone === "bad" ? "alert" : "document")}</span><div class="sq-grow"><div class="sq-file-t"><b>${esc(x.name)}</b><span class="pill ${tone}">${icon(glyph)}${esc(word)}</span></div><div class="note" id="${id}">${esc(reason)}</div></div>${act}</div>`;
    }).join("");
}
// The foot of the review: what was left alone, and the two things it opens (what the labels mean, the files left alone).
function sqFootHtml(f) {
  const S = sqState(), P = sqFiles(f), alone = [...P.before, ...P.copies];
  const left = [P.before.length ? `${plural(P.before.length, "file")} imported before` : "", P.copies.length ? `${P.copies.length === 1 ? "1 copy" : `${P.copies.length} copies`} of a file read` : "",
    f.other ? (f.other === 1 ? "1 other workbook that isn't an SQL listing or report" : `${f.other} other workbooks that aren't SQL listings or reports`) : ""].filter(Boolean);
  const tog = (attr, on, label, ctl) => `<button type="button" class="sq-linkbtn sq-tog" ${attr}="1" aria-expanded="${on}" aria-controls="${ctl}">${label}<span class="chev${on ? " on" : ""}" aria-hidden="true">${icon("chevronRight")}</span></button>`;
  return `<div class="sq-foot"><span class="sq-grow">${left.length ? `Left alone: ${left.join("; ")}.` : ""}</span>
      ${tog("data-sq-legend", S.legend, "What the labels mean", "sq-legend")}${alone.length ? tog("data-sq-left", S.left, S.left ? "Hide files" : "Show files", "sq-left") : ""}</div>
    ${S.legend ? `<div class="sq-list" id="sq-legend">${Object.values(SQ_STATUS).map(([w, t, g, m]) => `<div class="sq-list-r"><span class="sq-leg-w"><span class="pill ${t}">${icon(g)}${w}</span></span><span class="note">${m}</span></div>`).join("")}</div>` : ""}
    ${S.left && alone.length ? `<div class="sq-list" id="sq-left">${alone.map(x => `<div class="sq-list-r"><span class="sq-grow">${esc(x.name)}${x.status === "copy" && x.reason ? ` <span class="muted">· ${esc(x.reason.replace(/\.$/, "").replace(/^A copy/, "a copy"))}</span>` : ""}</span><span class="pill grey">${x.status === "copy" ? "A copy" : "Imported before"}</span></div>`).join("")}</div>` : ""}`;
}
function sqReviewHtml(f) {
  const P = sqFiles(f), listings = P.read.filter(x => !x.report), reports = P.read.filter(x => x.report && x.report !== "myinvois"), mi = P.read.filter(x => x.report === "myinvois");
  const lead = (listings.length ? `<b>${plural(listings.length, "listing")} read</b> from ${esc(f.folder)}: ${plural(f.entries, "document")}, <b>${f.new} new</b>, ${f.already} already imported.`
    : `No new SQL listing was found in ${esc(f.folder)}.`) + (reports.length ? ` <b>${plural(reports.length, "report")} of SQL's general ledger read.</b>` : "")
    + (mi.length ? ` <b>MyInvois e-Invoices: ${mi.reduce((a, x) => a + x.rows, 0)}</b>.` : "");
  const row = (x, glyph, meta, counts) => `<div class="sq-file">${icon(glyph)}<div class="sq-grow"><b>${esc(x.name)}</b><div class="note small">${meta}</div></div><span class="sq-counts">${counts}</span><span class="pill ok">${icon("check")}Read</span></div>`;
  return `<section class="card sq-card sq-review" aria-labelledby="sql-review-h">
    <div class="sq-review-top"><span class="sq-plate ok">${icon("search")}</span><div class="sq-grow"><h2 id="sql-review-h">What the fetch found</h2><span class="note">${lead}</span></div>
      ${listings.length ? `<div class="sq-chips"><span class="pill grey">${plural(f.entries, "document")}</span><span class="pill">${f.new} new</span><span class="pill grey">${f.already} already imported</span></div>` : ""}</div>
    ${listings.map(x => row(x, "document", `${esc(x.title)}${sqSpan(x)}`, `${x.new} new, ${x.already} already imported${x.repeated ? `, ${x.repeated} also in another file` : ""}`)).join("")}
    ${reports.map(x => row(x, "sheet", `${esc(GL_KIND[x.report] || x.title)}${sqSpan(x)}`, x.report === "journal" ? `${plural(x.docs, "document")}, ${plural(x.lines, "line")}` : plural(x.accounts, "account"))).join("")}
    ${mi.map(x => row(x, "verified", `MyInvois e-Invoices${sqSpan(x)}`, `${plural(x.rows, "e-Invoice")}: ${x.new} new, ${x.changed} status or details changed, ${x.unchanged} unchanged${x.older ? `, ${x.older} left as a later copy says` : ""} (${x.issued} issued, ${x.self_billed} self-billed, ${x.received} received)`)).join("")}
    ${sqUnusedHtml(P.unused)}${sqFootHtml(f)}</section>`;
}
// A fetch with nothing to import: why, and the ways on (paste one listing, another folder).
function sqNothingHtml(f) {
  const P = sqFiles(f), n = P.unused.length;
  const text = n ? `No new SQL listing was found in ${f.folder}. ${plural(n, "file")} ${n === 1 ? "was" : "were"} not used: see why below. Nothing was changed.`
    : `No new SQL listing was found in ${f.folder}. In SQL Account, export the listing and save it in SQL Drive, in the Download folder, then fetch again.`;
  return `<section class="card sq-card sq-review" aria-labelledby="sql-none-h">
    <div class="sq-review-top"><span class="sq-plate ${n ? "warn" : "mute"}">${icon(n ? "alert" : "folder")}</span><div class="sq-grow"><h2 id="sql-none-h">Nothing new to import</h2><span class="note">${esc(text)}</span></div>
      <div class="sq-none-go"><button type="button" class="sq-linkbtn" data-sq-paste-instead="1">Paste a listing instead</button><button type="button" class="ghost" data-sq-folder-fix="1">Use another folder</button><button type="button" class="ghost" id="sqlCancel">Close</button></div></div>
    ${sqUnusedHtml(P.unused)}${sqFootHtml(f)}</section>`;
}

// A customer invoice (IV) can be linked to the money-in payment it is for (the tenant's rent): the receipt then shows the
// invoice and its e-Invoice. Offered when the company has money in; the server suggests one by name and amount.
function receiptPick(p, r) {
  if (r.kind !== "invoice" || r.doc_type !== "IV") return "";
  const ins = p.candidates.filter(c => c.direction === "in");
  if (!ins.length) return "";
  return `<div class="sq-rcpt"><span class="note small">Receipt:</span><select class="sq-sel" data-sql-row="${r.row}" aria-label="Receipt that ${esc(r.doc_no)} is for"><option value="">Not linked</option>${paymentOptions(ins, { ...r, direction: "in" }, r.payment_id)}</select></div>`;
}
// What a row of the preview records: a payment to pick, the checklist item it is filed on, or what it is kept as.
function sqTarget(p, r) {
  if (r.exists) return `<span class="pill grey">Already imported</span>${r.before_tracking ? "" : receiptPick(p, r)}`;
  if (r.before_tracking) return `<span class="pill grey">${icon("history")}Before tracking, kept with SQL's books</span>`;
  if (r.kind !== "payment") return (r.task_id ? `<span class="pill ok">${icon("checklist")}Checklist: ${esc(r.task_title)}</span>`
    : `<span class="pill grey">${esc(r.label || (r.kind === "journal" ? "Journal" : "Invoice"))}, kept on file</span>`) + receiptPick(p, r);
  const none = !r.payment_id;
  return `<select class="sq-sel${none ? " warn" : ""}" data-sql-row="${r.row}" aria-label="Payment that ${esc(r.doc_no)} records"><option value="">Not linked</option>${paymentOptions(p.candidates, r, r.payment_id)}</select>${r.task_id ? `<div class="note small">Also: ${esc(r.task_title)}</div>` : ""}${changedInSql(r)}
    <div class="note small warn sq-nopay" data-sq-nopay="${r.row}"${none ? "" : " hidden"}>No payment yet. It will wait under entries not linked.</div>`;
}
// Beside Import: what importing will leave to do.
function sqImportNote(p) {
  if (!p.records.length) return p.ledger ? "Nothing is matched to payments: SQL's account lines are kept and checked against its reports." : "Nothing is matched to payments: the MyInvois e-Invoices read are kept.";
  const pay = p.records.filter(r => !r.exists && !r.before_tracking && r.kind === "payment" && !r.payment_id);
  const wait = pay.filter(r => !r.linked_to).length, ch = pay.filter(r => r.linked_to).length;
  return (wait ? `${wait} new ${wait === 1 ? "document has" : "documents have"} no payment yet. Import anyway: ${wait === 1 ? "it waits" : "they wait"} under SQL entries not linked to a payment.`
    : p.records.some(r => !r.exists) ? "Every new voucher is linked to a payment." : "Every document here was imported before.")
    + (ch ? ` ${ch} changed in SQL ${ch === 1 ? "waits" : "wait"} under Changed in SQL.` : "");
}
const sqPill = () => `<span class="pill sq-prev">${icon("eye")}Preview: nothing is saved yet</span>`;
function sqFoundHtml(p) {
  const S = sqState(), only = (p.ledger || p.myinvois) && !p.records.length;
  const blocked = p.ledger?.refused && !p.records.filter(r => !r.exists).length;
  const title = only ? (p.ledger ? "SQL's general-ledger reports" : "MyInvois e-Invoices") : sqTitle(p.filename);
  const found = (p.fields || []).filter(f => p.mapping?.[f] != null).map(f => SQL_FIELD_LABELS[f] ?? f);
  const colOpts = sel => `<option value="">(none)</option>` + p.headers.map((h, i) => `<option value="${i}" ${i === sel ? "selected" : ""}>${esc(h || "Column " + (i + 1))}</option>`).join("");
  const cols = !p.fetch && !only ? `<div class="sq-cols"><button type="button" class="sq-cols-b" data-sq-cols="1" aria-expanded="${S.cols}" aria-controls="sq-cols-p"><span class="chev${S.cols ? " on" : ""}" aria-hidden="true">${icon("chevronRight")}</span><b>Columns read</b>
      <span class="note">${esc(sqWords(found))} ${found.length === 1 ? "was" : "were"} found. Changing a column reads the rows again; payments you picked stay.</span></button>
    ${S.cols ? `<div class="sq-cols-p" id="sq-cols-p">${p.fields.map(f => `<label class="field"><span>${esc(SQL_FIELD_LABELS[f] ?? f)}</span><select data-sql-map="${f}">${colOpts(p.mapping[f])}</select></label>`).join("")}</div>` : ""}</div>` : "";
  const rows = p.records.map(r => {
    const sub = [r.kind !== "payment" ? r.label : "", r.payee].filter(Boolean).join(" · ");
    return `<tr class="${r.exists ? "sq-old" : ""}"><td class="mono sq-no">${esc(r.doc_no)}</td><td class="nowrap">${shortDate(r.date)}</td>
      <td>${esc(r.description)}${sub ? `<div class="note small">${esc(sub)}</div>` : ""}${sqlCodes(r)}${r.direction === "in" ? `<span class="pill ok sq-mi">Money in</span>` : ""}${r.einvoice || r.einvoice_status ? `<div>${einvPill(r)}</div>` : ""}</td>
      <td class="num${r.direction === "in" ? " sq-in" : ""}">${r.direction === "in" ? "+" : ""}${sqAmt(r.amount)}</td><td>${sqTarget(p, r)}</td></tr>`;
  }).join("");
  return `${p.fetch ? sqReviewHtml(p.fetch) : ""}<section class="card sq-card sq-res" aria-labelledby="sql-preview-h">
    <div class="sq-res-top"><h2 id="sql-preview-h">${esc(title)}</h2>${sqPill()}<span class="note">${only ? "No new listing entries" : `${p.records.length} entries found`}</span></div>
    ${(p.signed_off || []).length ? `<div class="sq-warnbox" role="note">${icon("lock")}<span>New entries fall in ${p.signed_off.map(m => esc(monthName(m))).join(", ")}, whose bank reconciliation is signed off: its book figures may change. Nothing is un-signed: check ${p.signed_off.length === 1 ? "that month" : "those months"} again after importing.</span></div>` : ""}
    ${sqlLedgerBox(p.ledger)}
    ${only ? "" : `<p class="sq-note">${p.fetch ? "Check each suggested payment, then import. The new documents are listed first." : "Check the columns were read correctly, then check each suggested payment."}</p>`}
    ${cols}
    ${only ? "" : `<div class="tbl-wrap sq-tw"><table class="sq-tbl sq-ptbl"><thead><tr><th>Doc no.</th><th>Date</th><th>Description</th><th class="num">Amount (RM)</th><th>Records this payment</th></tr></thead><tbody>${rows}</tbody></table></div>`}
    <div class="sq-ibar"><span class="sq-inote" id="sq-inote" role="status">${esc(sqImportNote(p))}</span><div class="sq-ibar-go"><button type="button" class="ghost" id="sqlCancel">Cancel</button>
      <button type="button" class="btn" id="sqlApply" ${blocked ? "disabled" : ""}>${icon("check")}<span id="sq-apply-t">${applyLabel(p)}</span></button></div></div></section>`;
}
// The lines of a journal: kept for the bank reconciliation, nothing to match. Lines pasted as plain text carry no
// document key, so the person says which journal they are from.
function sqJournalHtml(p) {
  const jl = p.journal_lines, ok = !jl.text_form || (jl.balanced && jl.chosen);
  const pick = !jl.text_form ? "" : !jl.balanced ? `<div class="sq-alert" role="alert">${icon("alert")}<span class="sq-grow">${esc(jl.message)}</span></div>` : `
    <label class="field sq-jpick"><span>Which journal are these lines from?</span><select id="sqlJournalPick"><option value="">Choose a journal</option>${jl.options.map(o =>
      `<option value="${o.id}" ${o.id === jl.chosen ? "selected" : ""}>${esc(o.doc_no)}, ${esc(o.doc_date)}, ${sqAmt(o.amount)}${o.match ? " (same total)" : ""}</option>`).join("")}</select></label>
    ${jl.message ? `<p class="note">${esc(jl.message)}</p>` : ""}`;
  return `<section class="card sq-card sq-res" aria-labelledby="sql-jl-h">
    <div class="sq-res-top"><h2 id="sql-jl-h">${esc(sqTitle(p.filename))}</h2>${sqPill()}<span class="note">${jl.lines} journal lines found</span></div>
    <p class="sq-note">${jl.text_form ? "These are a journal's lines, pasted as text." : "These are journal lines, each with the journal it belongs to."} They are kept for the bank reconciliation; nothing is matched to payments.</p>
    <div class="sq-jbody">${pick}${jl.notes.map(n => `<div class="sq-jnote">${icon("bank")}<span>${esc(n.text)}</span></div>`).join("")}</div>
    <div class="sq-ibar"><span class="sq-grow"></span><div class="sq-ibar-go"><button type="button" class="ghost" id="sqlCancel">Cancel</button><button type="button" class="btn" id="sqlApply" ${ok ? "" : "disabled"}>${icon("check")}Keep ${jl.lines} journal lines</button></div></div></section>`;
}
// After Import: what was done, in place of the preview, with the way to what is left to do.
function sqDoneHtml(x) {
  const [glyph, label, to, go] = { import: ["verified", "Import result", "sql-unlinked-h", "See entries not linked"], reports: ["sheet", "Account lines kept", "sql-checks-h", "See Checks against SQL's reports"],
    lines: ["bank", "Journal lines kept", "sql-docs-h", "See the journal"], einv: ["verified", "MyInvois e-Invoices kept", "sqlEinvoices", "See e-Invoices"] }[x.kind];
  return `<section class="sq-done" aria-label="${label}"><span class="sq-plate ok">${icon(glyph)}</span><div class="sq-grow" role="status"><b>${esc(x.title)}</b><div class="note">${esc(x.text)}</div></div>
    <div class="sq-done-go">${x.changed ? `<button type="button" class="ghost" data-sq-jump="sb-changed-h">See Changed in SQL</button>` : ""}<button type="button" class="btn" data-sq-jump="${to}">${go}${icon("arrow")}</button>
      <button type="button" class="ghost icon-only" data-sq-done-close="1" aria-label="Close this message">${icon("close")}</button></div></section>`;
}
function sqReadingHtml(from) {
  return `<section class="card sq-card sq-reading" aria-label="Reading" aria-busy="true"><div class="sq-reading-t"><span class="spin sq-spin" aria-hidden="true"></span><b>${from === "fetch" ? "Reading the folder…" : from === "paste" ? "Reading the pasted rows…" : "Reading the file…"}</b></div>
    <span class="sk" style="height:16px;width:46%"></span><span class="sk" style="height:44px"></span><span class="sk" style="height:44px"></span><span class="sk" style="height:44px;width:72%"></span></section>`;
}
function sqResultHtml() {
  const S = sqState(), p = sqPreviewNow();
  const preview = () => p.nothing_new ? sqNothingHtml(p.fetch) : p.journal_lines ? sqJournalHtml(p) : sqFoundHtml(p);
  // While reading, the preview shown before stays under the skeleton, dimmed and out of reach, until the new one arrives.
  if (S.reading) return sqReadingHtml(S.reading) + (p ? `<div class="sq-dim" inert aria-hidden="true">${preview()}</div>` : "");
  if (p) return preview();
  return S.done ? sqDoneHtml(S.done) : "";
}

/* ---------------- The lower half: the entries, Journals and invoices, the checks, Imported files ---------------- */
const sqlText = x => [x.doc_no, fmtDate(x.doc_date), x.doc_date, x.description, x.payee, x.code, x.cheque_no, x.payment_method, LT.amount(x.amount), x.direction === "in" ? "money in" : "", x.payment_desc,
  x.payment_month ? monthName(x.payment_month) : "", x.einvoice ? "e-invoice" : ""].join(" ");
function sqEntriesHtml(d) {
  const S = sqState(), q = listState("sql").q.trim();
  const candOpts = u => `<option value="">Choose a payment…</option>${paymentOptions(d.candidates, u, S.sel[u.id] ? +S.sel[u.id] : undefined)}`;
  // A voucher changed in SQL whose earlier entry is linked: shown once, under Changed in SQL, until the owner moves the link.
  const changedIds = new Set((d.changed || []).map(x => x.new.id));
  const waiting = d.unlinked.filter(u => !u.correction && !changedIds.has(u.id)), corrections = d.unlinked.filter(u => u.correction && !changedIds.has(u.id));
  state.sqlCorrections = corrections.map(u => u.id);
  const before = d.before_tracking || [], replaced = d.superseded || [];
  const w = listRows("sql", waiting, sqlText), c = listRows("sql", corrections, sqlText), lk = listRows("sql", d.linked, sqlText), ig = listRows("sql", d.ignored, sqlText),
    bf = listRows("sql", before, sqlText);
  const total = waiting.length + corrections.length + d.linked.length + d.ignored.length + before.length, shown = w.length + c.length + lk.length + ig.length + bf.length;
  setCount("sql", shown, total); S.count = [shown, total];
  // Entries of the import just made are marked, so they can be found in the lists.
  const fresh = S.done?.kind === "import" ? d.imports[0]?.id : null, isNew = x => fresh != null && x.import_id === fresh;
  const desc = (x, pills = []) => `${esc(x.description)}${x.payee ? `<div class="note small">${esc(x.payee)}</div>` : ""}${sqlCodes(x)}<div class="sq-pills">${[isNew(x) ? `<span class="pill">Just imported</span>` : "", linesPill(d.lines, x), ...pills].join("")}</div>`;
  const amt = x => `<td class="num${x.direction === "in" ? " sq-in" : ""}">${x.direction === "in" ? "+" : ""}${sqAmt(x.amount)}</td>`;
  const th = (cols, last) => `<thead><tr>${sortTh("sql", "doc", "Doc no.")}${sortTh("sql", "date", "Date")}${sortTh("sql", "desc", "Description")}${sortTh("sql", "amount", "Amount (RM)", "num")}${cols}${last}</tr></thead>`;
  const unRow = u => `<tr><td class="mono sq-no">${esc(u.doc_no)}</td><td class="nowrap">${shortDate(u.doc_date)}</td>
      <td>${desc(u, [u.direction === "in" ? `<span class="pill ok">Money in</span>` : "", u.einvoice ? `<span class="pill ok">e-Invoice ${esc(u.einvoice.slice(0, 8))}…</span>` : ""])}${changedInSql(u)}</td>${amt(u)}
      <td><div class="sq-link"><select class="sq-sel" data-sql-link="${u.id}" aria-label="Payment to link ${esc(u.doc_no)} to">${candOpts(u)}</select><button type="button" class="ghost small" data-sql-link-go="${u.id}" aria-label="Link ${esc(u.doc_no)}"${S.sel[u.id] ? "" : " disabled"}>Link</button></div></td>
      <td><div class="sq-acts"><button type="button" class="ghost small" data-sql-create="${u.id}" aria-label="Create payment for ${esc(u.doc_no)}">Create payment</button><button type="button" class="sq-quiet" data-sql-ignore="${u.id}" aria-label="Ignore ${esc(u.doc_no)}">Ignore</button></div></td></tr>`;
  const none = (list, text) => list.length ? sqNone("search", "mute", "No entry matches.") : sqNone("check", "ok", text);
  const ask = (label, text, rest, no, yes, yesLabel) => `<div class="sq-ask" role="group" aria-label="${label}">${icon("alert")}<span class="sq-grow"><b>${text}</b> ${rest}</span>
    <div class="sq-ask-go"><button type="button" class="ghost small" data-sq-ask="${no}">Cancel</button><button type="button" class="btn small" id="sq-${yes}" data-sq-ask="${yes}">${yesLabel}</button></div></div>`;
  const changedCard = (d.changed || []).length ? `<section class="card sq-card sq-changed" id="sb-changed" aria-labelledby="sb-changed-h">
      <div class="sq-head warn"><span class="sq-ic warn">${icon("alert")}</span><div class="sq-grow"><h2 id="sb-changed-h" tabindex="-1">Changed in SQL</h2><span class="note">These vouchers were edited in SQL after they were linked to a payment: the latest fetch gives another amount or date. The link stays on the earlier entry until you move it. Moving it keeps the earlier entry, marked as replaced.</span></div></div>
      ${d.changed.map(x => `<div class="sq-ch" role="group" aria-labelledby="sq-ch-${x.old.id}" data-sql-changed="${x.old.id}">
        <div id="sq-ch-${x.old.id}"><b class="mono">${esc(x.doc_no)}</b> changed in SQL ${esc(x.words)}.</div>
        <div class="note">Linked to ${esc(x.payment.description)}${x.payment.month_label ? ` (${esc(x.payment.month_label)})` : ""}, whose amount is ${money(x.payment.amount)}.${x.ledger ? (x.ledger.agrees ? ` SQL's GL Journal of Transaction (version ${x.ledger.version}) already has ${money(x.ledger.total)}.` : ` SQL's GL Journal of Transaction kept here still has ${money(x.ledger.total)}: fetch it again for the same dates so the account lines follow.`) : ""}</div>
        ${x.amount_follows ? `<label class="sq-check"><input type="checkbox" data-sql-follow="1"> Also change the payment's amount from ${money(x.old.amount)} to ${money(x.new.amount)}</label>` : ""}
        <div><button class="ghost small" type="button" data-sql-move="${x.old.id}" data-sql-move-to="${x.new.id}">Move the link to the new amount</button></div></div>`).join("")}</section>` : "";
  const unlinked = `<section class="card sq-card" id="sql-unlinked" aria-labelledby="sql-unlinked-h">
      ${sqHead("sql-unlinked-h", "inbox", "warn", "SQL entries not linked to a payment", waiting.length, "These are in SQL but not in HR Payments. Link each one to a payment, create a payment for it, or ignore it (for example a reversal).",
        waiting.length > 1 && !S.confirmAll ? `<button type="button" class="ghost small" id="sqlCreateAll">Create payments for all ${waiting.length}</button>` : "")}
      ${S.confirmAll && waiting.length > 1 ? ask("Create payments for all", `Create ${waiting.length} payments?`, "Each one takes its voucher's date, description and amount. A voucher whose number is typed on a payment is linked to that payment instead; one whose number is already linked is left for you to check. Probable corrections are left out.", "all-no", "all-yes", `Create ${waiting.length} payments`) : ""}
      ${w.length ? `<div class="tbl-wrap sq-tw"><table class="sq-tbl sq-utbl">${th(`<th>Link to</th>`, `<th>Or</th>`)}<tbody>${w.map(unRow).join("")}</tbody></table></div>` : none(waiting, "Nothing waiting. Every SQL entry is linked to a payment or ignored.")}
      ${corrections.length ? `<div class="sq-sub"><div class="sq-grow"><h3>Probably a correction (no money moved)</h3><span class="note">Reversals and contras made in SQL, or a receipt and a payment for the same amount on the same day. Create payments for all leaves these out. Ignore them, unless money really moved.</span></div>
          ${S.confirmIgnore ? "" : `<button type="button" class="ghost small" id="sqlIgnoreAll">Ignore all ${corrections.length}</button>`}</div>
        ${S.confirmIgnore ? ask("Ignore all probable corrections", `Ignore ${corrections.length} probable corrections?`, "They move to Ignored, below. Un-ignore one there if money really moved.", "ign-no", "ign-yes", `Ignore all ${corrections.length}`) : ""}
        ${c.length ? `<div class="tbl-wrap sq-tw"><table class="sq-tbl sq-utbl">${th(`<th>Link to</th>`, `<th>Or</th>`)}<tbody>${c.map(unRow).join("")}</tbody></table></div>` : sqNone("search", "mute", "No entry matches.")}` : ""}
    </section>`;
  const open = k => state.sqlOpen[k] === true || (state.sqlOpen[k] !== false && !!q && (k === "linked" ? lk : k === "ignored" ? ig : bf).length > 0);
  const linked = sqFold("linked", "link", "ok", "Linked to payments", d.linked.length, open("linked"),
    lk.length ? `<div class="tbl-wrap sq-tw"><table class="sq-tbl">${th(sortTh("sql", "pay", "Payment"), `<th><span class="sr-only">Action</span></th>`)}<tbody>
      ${lk.map(x => `<tr><td class="mono sq-no">${esc(x.doc_no)}</td><td class="nowrap">${shortDate(x.doc_date)}</td><td>${desc(x)}</td>${amt(x)}
        <td><b>${esc(x.payment_desc)}</b> <span class="muted">(${monthName(x.payment_month)})</span></td><td class="sq-act"><button type="button" class="ghost small" data-sql-unlink="${x.id}" aria-label="Unlink ${esc(x.doc_no)}">Unlink</button></td></tr>`).join("")}</tbody></table></div>`
      : sqNone(d.linked.length ? "search" : "inbox", "mute", d.linked.length ? "No entry matches." : "None yet."),
    "Linked to the wrong payment? Unlink it: it goes back to the list above, and the payment's amount and paid date go back to what they were. A payment made from the voucher with Create payment, with nothing added since, is removed.");
  // Under Ignored, one confirmed as deleted in SQL says so, with the day it was confirmed.
  const ignored = d.ignored.length ? sqFold("ignored", "archive", "mute", "Ignored", d.ignored.length, state.sqlOpen.ignored !== false,
    ig.length ? `<div class="tbl-wrap sq-tw"><table class="sq-tbl">${th("", `<th><span class="sr-only">Action</span></th>`)}<tbody>
      ${ig.map(x => `<tr><td class="mono sq-no">${esc(x.doc_no)}</td><td class="nowrap">${shortDate(x.doc_date)}</td><td>${desc(x, [x.deleted_in_sql ? `<span class="pill grey sq-del">${icon("trash")}Deleted in SQL ${esc(shortDate(x.deleted_in_sql))}</span>` : ""])}</td>${amt(x)}
        <td class="sq-act"><button type="button" class="ghost small" data-sql-unignore="${x.id}" aria-label="Un-ignore ${esc(x.doc_no)}">Un-ignore</button></td></tr>`).join("")}</tbody></table></div>` : sqNone("search", "mute", "No entry matches.")) : "";
  const beforeCard = before.length ? sqFold("before", "history", "mute", `Before tracking (${before.length})`, null, open("before"),
    bf.length ? `<div class="tbl-wrap sq-tw"><table class="sq-tbl">${th("", "")}<tbody>
      ${bf.map(x => `<tr><td class="mono sq-no">${esc(x.doc_no)}</td><td class="nowrap">${shortDate(x.doc_date)}</td><td>${desc(x)}</td>${amt(x)}</tr>`).join("")}</tbody></table></div>` : sqNone("search", "mute", "No entry matches."),
    `These SQL entries are from months before ${d.first_month ? esc(monthName(d.first_month)) : "the first month tracked"}, the first month tracked here. They are kept with SQL's books (their account lines and the checks against SQL's reports) but are not tracked as payments, so nothing asks you to link them.`) : "";
  const replacedCard = replaced.length ? sqFold("replaced", "history", "mute", "Replaced by a later version from SQL", replaced.length, !!state.sqlOpen.replaced,
    `<div class="tbl-wrap sq-tw"><table class="sq-tbl"><thead><tr><th>Doc no.</th><th>Date</th><th>Description</th><th class="num">Amount then (RM)</th><th class="num">Amount now (RM)</th></tr></thead><tbody>
      ${replaced.map(x => `<tr><td class="mono sq-no">${esc(x.doc_no)}</td><td class="nowrap">${shortDate(x.doc_date)}${x.new_date !== x.doc_date ? `<div class="note small">now ${shortDate(x.new_date)}</div>` : ""}</td><td>${esc(x.description)}</td><td class="num">${sqAmt(x.amount)}</td><td class="num">${sqAmt(x.new_amount)}</td></tr>`).join("")}
      </tbody></table></div>`, "Earlier entries of vouchers edited in SQL. They are kept as they were read; the later entry is the one that counts.") : "";
  return changedCard + unlinked + linked + ignored + beforeCard + replacedCard;
}
function sqPaintCount() {
  const el = $("#sq-count"), [n, m] = sqState().count;
  if (el) el.textContent = listState("sql").q.trim() ? `Showing ${n} of ${m} SQL entries` : `${m} SQL ${m === 1 ? "entry" : "entries"}`;
}

// Journals, customer invoices and supplier invoices kept on file: each one's checklist item, the payment or receipt
// it is linked to, and for a journal that moves the bank, a payment to link it to.
function sqDocsHtml(d) {
  const S = sqState(), fresh = S.done?.kind === "import" ? d.imports[0]?.id : null;
  const candOpts = u => `<option value="">Choose a payment…</option>${paymentOptions(d.candidates, u, S.sel[u.id] ? +S.sel[u.id] : undefined)}`;
  const rows = d.documents.map(x => {
    const sub = [x.kind === "invoice" && x.doc_type !== "IV" ? x.label : "", x.payee].filter(Boolean).join(" · ");
    const linkable = x.kind === "journal" && x.bank_move != null && !x.before_tracking && !x.payment_id;
    return `<tr><td class="mono sq-no">${esc(x.doc_no)}</td><td class="nowrap">${shortDate(x.doc_date)}</td>
      <td>${esc(x.description)}${sub ? `<div class="note small">${esc(sub)}</div>` : ""}${sqlCodes(x)}<div class="sq-pills">${fresh != null && x.import_id === fresh ? `<span class="pill">Just imported</span>` : ""}${linesPill(d.lines, x)}</div></td>
      <td class="num">${sqAmt(x.amount)}</td><td>${einvPill(x)}${invoiceBtn(x)}</td>
      <td>${x.task_title ? `<span class="pill ok">${icon("checklist")}${esc(x.task_title.split(":")[0])} (${esc(sqMonth(x.task_month))})</span>` : x.before_tracking ? `<span class="pill grey">${icon("history")}Before tracking</span>` : `<span class="muted">—</span>`}
        ${x.kind === "journal" && x.bank_move != null ? `<div class="note">Moves ${money(Math.abs(x.bank_move))} ${x.bank_move > 0 ? "into" : "out of"} the bank, so it counts in the bank reconciliation.</div>` : ""}
        ${x.payment_id ? `<div class="sq-link"><span class="note">${x.kind === "journal" ? "Payment" : "Receipt"}: ${esc(x.payment_desc)}</span><button type="button" class="ghost small" data-sql-unlink="${x.id}" aria-label="Unlink ${esc(x.doc_no)}">Unlink</button></div>`
          : linkable ? `<div class="sq-link"><select class="sq-sel" data-sql-link="${x.id}" aria-label="Payment to link ${esc(x.doc_no)} to">${candOpts({ id: x.id, doc_no: x.doc_no, direction: x.bank_move > 0 ? "in" : "out" })}</select><button type="button" class="ghost small" data-sql-link-go="${x.id}" aria-label="Link ${esc(x.doc_no)}"${S.sel[x.id] ? "" : " disabled"}>Link</button><button type="button" class="ghost small" data-sql-create="${x.id}" aria-label="Create payment for ${esc(x.doc_no)}">Create payment</button></div>` : ""}</td></tr>`;
  }).join("");
  return `<section class="card sq-card" id="sql-docs" aria-labelledby="sql-docs-h">
    ${sqHead("sql-docs-h", "receipt", "brand", "Journals and invoices", null, "Journals, customer invoices and supplier invoices, kept on file against their checklist item. A journal that moves the bank counts in the bank reconciliation.")}
    <div id="invPrint" class="sq-print">${invoicePrintBar(d.invoice_print)}</div>
    <div class="tbl-wrap sq-tw"><table class="sq-tbl sq-dtbl"><thead><tr><th>Doc no.</th><th>Date</th><th>Description</th><th class="num">Amount (RM)</th><th>e-Invoice</th><th>Checklist item</th></tr></thead><tbody>
      ${rows || `<tr><td colspan="6" class="empty">Fetch SQL's Journal Voucher and Customer Invoice listings on this page to see them here.</td></tr>`}</tbody></table></div></section>`;
}
// The e-Invoices card, as it was before this page was rebuilt: it moves to its own page with slice 6.
function sqEinvoicesHtml(d) {
  return `<div class="card" id="sqlEinvoices"><h2>e-Invoices</h2><div class="note">Every SQL document with an e-Invoice, and whether LHDN has validated it. Where a copy of SQL's MyInvois Transaction screen was read, what MyInvois says is shown beside it.</div>
      <div class="tbl-wrap"><table><thead><tr><th>Doc No</th><th>Date</th><th>Description</th><th class="num">Amount</th><th>Status</th><th>MyInvois</th><th></th></tr></thead><tbody>
      ${d.einvoices.map(x => `<tr><td class="mono">${esc(x.doc_no)}</td><td>${shortDate(x.doc_date)}</td><td>${esc(x.payee || x.description)}</td><td class="num">${money(x.amount)}</td><td>${einvPill(x)}</td>
        <td>${x.myinvois ? `<span class="mono">${esc(x.myinvois.uuid)}</span><div class="note">${esc(x.myinvois.type || "")} · ${esc(x.myinvois.status)}${x.myinvois.validated_at ? ` · validated ${esc(x.myinvois.validated_at)}` : ""}</div>` : `<span class="muted">—</span>`}</td>
        <td><div class="row" style="gap:6px">${x.payment_id ? `<button class="ghost small" data-sql-unlink="${x.id}">Unlink</button>` : ""}${invoiceBtn(x)}</div></td></tr>`).join("") || `<tr><td colspan="7" class="empty">None imported yet.</td></tr>`}
      </tbody></table></div>
      <div id="miBox">${myinvoisBox(d.myinvois)}</div></div>`;
}
function sqImportsHtml(d) {
  const S = sqState(), glyph = n => /^SQL listing pasted/.test(n) ? "clipboard" : /^SQL (exports|reports) fetched/.test(n) ? "folder" : "document";
  return `<section class="card sq-card" id="sq-imports" aria-labelledby="sq-imports-h">
    ${sqHead("sq-imports-h", "history", "brand", "Imported files", null, "A fetch keeps the listings it read, so the evidence for each import stays with it.")}
    ${d.imports.length ? `<ul class="sq-imports">${d.imports.map((i, k) => `<li>${icon(glyph(i.filename))}<span class="sq-grow"><b>${esc(i.filename)}</b><span class="muted"> · ${i.entries} entries, ${i.linked} linked${i.lines ? ` · ${plural(i.lines, "line")}` : ""}</span></span><span class="muted sq-when">${k === 0 && S.done ? "Just now" : esc(sqWhen(i.imported_at))}</span></li>`).join("")}</ul>`
      : sqNone("inbox", "mute", "None yet.")}</section>`;
}

async function viewSql(main) {
  const e = ent();
  if (!e.uses_sql) { main.innerHTML = unusedCard("sql", e); return; }  // render() shows this card before; kept for a direct call
  const d = await api(`/api/sql/entries?entity=${state.entity}`);
  state.sqData = d;
  state.miData = d.myinvois;
  state.invPrint = d.invoice_print;
  const S = sqState();
  // A question asked before (Create payments for all, Ignore all) never comes back armed; an import's result stays only while
  // the page is drawn again after it, not when it is opened again from another page.
  S.confirmAll = false; S.confirmIgnore = false;
  if (render.last !== `sql:${state.entity}`) { S.done = null; S.arrive = false; }
  // Find an SQL entry: the shared list bar (its search and count), worded as the board has it.
  const bar = listBar("sql", "SQL entries").replace('placeholder="Search SQL entries"', 'placeholder="Find an SQL entry: doc no., description, amount or payment"')
    .replace('data-count="sql"', 'id="sq-count" data-count="sql"');
  main.innerHTML = `<div class="sq" id="sq">
    <div class="pg-head"><div class="pg-words"><span class="eyebrow">${esc(e.code)} · ${esc(keptLabel(e))}</span><h1 id="pg-h1" tabindex="-1">SQL import</h1>
      <p class="sq-lede">Fetch (or paste) each SQL listing for the month: <b>Cash Book</b>, <b>Receipt Voucher</b>, <b>Payment Voucher</b>, <b>Journal</b> and <b>Customer Invoice</b>. Payments and receipts are matched to the payments in HR Payments; customer invoices are filed against their checklist item of their own month and linked to the money in they are for, and a payroll journal against Salary PVs in SQL. A document that appears in two listings is only kept once, so overlap is fine.</p></div></div>
    <div id="sq-steps">${sqStepsHtml()}</div>
    <section class="card sq-card sq-fetch" id="sq-fetch" aria-labelledby="sq-fetch-h">${sqFetchInner()}</section>
    <section class="card sq-card sq-bring" id="sql-paste" aria-label="Bring in one listing yourself">${sqBringInner()}</section>
    <div id="sqlPreview" class="sq-result" tabindex="-1">${sqResultHtml()}</div>
    <section class="card sq-find" aria-label="Find an SQL entry">${icon("search")}${bar}</section>
    <div id="sqlEntries" class="sq">${sqEntriesHtml(d)}</div>
    ${sqDocsHtml(d)}
    <div id="sq-checks-wrap" class="sq">${sqlChecksCard(d)}</div>
    ${sqEinvoicesHtml(d)}
    ${sqImportsHtml(d)}</div>`;
  // A listing pasted but not imported yet stays, with links picked by hand, while you tidy the entries below.
  const box = $("#sqlPaste");
  if (box) box.value = state.sqlPaste[state.entity] || "";
  LIST_REDRAW.sql = () => { const el = $("#sqlEntries"); if (el && state.sqData) el.innerHTML = sqEntriesHtml(state.sqData); sqPaintCount(); };
  sqPaintCount();
  if (S.arrive) { S.arrive = false; sqArrive(); }
}

/* ---------------- Drawing a part again, and bringing the result into view ---------------- */
function sqPaint(part) {
  const at = { fetch: ["#sq-fetch", sqFetchInner], bring: ["#sql-paste", sqBringInner], result: ["#sqlPreview", sqResultHtml], steps: ["#sq-steps", sqStepsHtml],
    entries: ["#sqlEntries", () => state.sqData ? sqEntriesHtml(state.sqData) : ""], checks: ["#sq-checks-wrap", () => state.sqData ? sqlChecksCard(state.sqData) : ""] }[part];
  const el = at && $(at[0]);
  if (!el) return;
  el.innerHTML = at[1]();
  if (part === "bring") { const box = $("#sqlPaste"); if (box) box.value = state.sqlPaste[state.entity] || ""; }
  if (part === "entries") sqPaintCount();
}
// The Fetch button changes in place, so the focus stays on it while the folder is read.
function sqFetchBtnPaint() {
  const b = $("#sqlFetch");
  if (!b) return;
  const f = sqFetchParts();
  b.className = f.cls; b.innerHTML = f.inner; b.setAttribute?.("aria-busy", String(f.busy));
  if (f.busy) b.setAttribute?.("aria-disabled", "true"); else b.removeAttribute?.("aria-disabled");
  const hint = $("#sq-fetch-hint");
  if (hint) hint.textContent = sqState().reading === "fetch" ? "Opening each workbook in the folder" : "Nothing in the folder is moved or changed";
}
const sqCalm = () => typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
// A result has arrived below the fold: bring it into view and move the focus to it.
function sqArrive() {
  const el = $("#sqlPreview");
  el?.scrollIntoView?.({ behavior: sqCalm() ? "auto" : "smooth", block: "start" });
  el?.focus?.({ preventScroll: true });
}
function sqJump(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.scrollIntoView?.({ behavior: sqCalm() ? "auto" : "smooth", block: "start" });
  el.focus?.({ preventScroll: true });
}

// The preview of what was read (a fetch, a paste, a file, journal lines); arrive: it is new, so it is brought into view.
function renderSqlPreview(p, { arrive = false } = {}) {
  state.sqlPreview = p;
  const S = sqState();
  S.reading = null; S.done = null; S.cols = S.cols && !arrive;
  sqPaint("result"); sqPaint("steps"); sqFetchBtnPaint();
  if (S.mode === "paste" || S.mode === "file") sqReadBtnsPaint();
  if (arrive) sqArrive();
}
function sqReadBtnsPaint() {
  const S = sqState();
  for (const [id, label, from] of [["sq-read-paste", "Read pasted rows", "paste"], ["sq-read-file", "Read file", "file"]]) {
    const b = $(`#${id}`);
    if (!b || b.isConnected === false) continue;
    const busy = S.reading === from;
    b.setAttribute?.("aria-busy", String(busy));
    if (S.reading) b.setAttribute?.("aria-disabled", "true"); else b.removeAttribute?.("aria-disabled");
    b.innerHTML = busy ? `<span class="spin sq-spin" aria-hidden="true"></span>${from === "paste" ? "Reading the rows…" : "Reading the file…"}` : label;
  }
}

/* ---------------- What the buttons do ---------------- */
async function sqlFetch() {
  const S = sqState();
  if (S.reading) return;
  // The preview shown (and the payments picked in it) stays until the new read arrives: a failed read leaves it as it was.
  const was = S.done;
  // A fetch closes the folder box and takes the old notes away: the fetch card is drawn again (the focus stays on Fetch).
  const card = S.folderEdit || S.folderMsg || S.folderErr || S.fetchErr;
  Object.assign(S, { reading: "fetch", fetchErr: "", done: null, folderEdit: false, folderMsg: "", folderErr: "" });
  if (card) { sqPaint("fetch"); $("#sqlFetch")?.focus?.(); }
  sqPaint("result"); sqFetchBtnPaint();
  try { renderSqlPreview(await api("/api/sql/preview", { json: { entity_id: state.entity, fetch: true } }), { arrive: true }); }
  catch (e) {
    S.reading = null; S.done = was;
    if (appStopped(e)) { sqPaint("fetch"); sqPaint("result"); throw e; }
    S.fetchErr = e.message; sqPaint("fetch"); sqPaint("result"); $("#sqlFetch")?.focus?.();
  }
}
// Read pasted rows / Read file: what is wrong is said under the box, in place; the preview comes into view.
async function sqlRead(kind) {
  const S = sqState();
  if (S.reading) return;
  let body;
  if (kind === "paste") {
    const text = $("#sqlPaste")?.value || "";
    state.sqlPaste[state.entity] = text;
    if (!text.trim()) { S.pasteErr = "Paste the rows copied from SQL first."; sqPaint("bring"); return $("#sqlPaste")?.focus?.(); }
    body = { json: { entity_id: state.entity, text } };
  } else {
    const f = S.file;  // one refused when chosen is never sent
    if (!f) { S.fileErr = S.fileErr || "Choose the SQL export file first."; sqPaint("bring"); return $("#sqlFile")?.focus?.(); }
    const fd = new FormData(); fd.append("file", f); fd.append("entity_id", state.entity);
    body = { form: fd };
  }
  const was = S.done;  // the preview shown stays until the new one arrives (see sqlFetch)
  Object.assign(S, { reading: kind, done: null, pasteErr: "", fileErr: "" });
  sqReadBtnsPaint(); sqPaint("result"); sqFetchBtnPaint();
  try { renderSqlPreview(await api("/api/sql/preview", body), { arrive: true }); }
  catch (e) {
    S.reading = null; S.done = was;
    if (appStopped(e)) { sqPaint("result"); sqReadBtnsPaint(); throw e; }
    if (kind === "paste") S.pasteErr = e.message; else S.fileErr = e.message;
    sqPaint("bring"); sqPaint("result"); sqFetchBtnPaint();
    (kind === "paste" ? $("#sqlPaste") : $("#sqlFile"))?.focus?.();
  }
}
// What an import did, said in place of the preview (the board's result), not in a toast that goes after a few seconds.
function sqDone(p, res) {
  if (res.journal_lines) {
    const o = (p.journal_lines?.options || []).find(x => x.id === p.journal_lines?.chosen);
    return { kind: "lines", src: "paste", title: `Kept ${res.journal_lines} journal lines`, text: o ? `They are kept with ${o.doc_no}.` : "They are kept with the journals they belong to, for the bank reconciliation." };
  }
  const kept = res.ledger?.files || [], docs = kept.filter(f => f.kind === "journal").reduce((a, f) => a + (f.summary?.docs || 0), 0),
    diffs = kept.reduce((a, f) => a + (f.problems || 0), 0);
  const lines = kept.length ? `Kept the account lines of ${plural(docs, "document")} from ${plural(kept.length, "report")} of SQL's general ledger${diffs ? `; ${plural(diffs, "difference")} from SQL's reports, listed under Checks against SQL's reports` : ""}` : "";
  const moved = res.recon_changed?.length ? `. The bank reconciliation of signed-off ${res.recon_changed.map(m => monthName(m.month)).join(", ")} changed: it stays signed off; check it again` : "";
  const mi = res.myinvois, miFilled = mi ? mi.notes.filter(x => x.includes("filled in from MyInvois")).length : 0;
  const einv = mi ? `Kept ${plural(mi.files.reduce((a, f) => a + f.rows, 0), "MyInvois e-Invoice")} (${mi.files.reduce((a, f) => a + f.new, 0)} new, ${mi.files.reduce((a, f) => a + f.changed, 0)} changed); ${plural(miFilled, "SQL document")} filled in` : "";
  const src = p.fetch ? "fetch" : /^SQL listing pasted/.test(p.filename || "") ? "paste" : "file";
  if (!p.records.length && (kept.length || mi))
    return { kind: kept.length ? "reports" : "einv", src, title: kept.length ? "Kept the account lines" : "Kept the MyInvois e-Invoices", text: [lines, einv].filter(Boolean).join(". ") + moved + "." };
  // Vouchers edited in SQL: one linked to nothing replaced its earlier entry; one linked waits under Changed in SQL.
  const edits = `${res.replaced?.length ? `. Changed in SQL, listed once at the new figure: ${res.replaced.join(", ")}` : ""}${res.changed_linked ? `. ${res.changed_linked} linked ${res.changed_linked === 1 ? "voucher was" : "vouchers were"} changed in SQL: see Changed in SQL` : ""}`;
  return { kind: "import", src, changed: !!res.changed_linked, title: `Imported ${res.added} entries`,
    text: `${res.linked} linked to payments${res.skipped ? `, ${res.skipped} already imported` : ""}${matchedNote(res)}${lines ? `. ${lines}` : ""}${einv ? `. ${einv}` : ""}${edits}${moved}${heldNote(res.held)}.` };
}
async function sqlApply(t) {
  const p = state.sqlPreview;
  if (!p || t.getAttribute?.("aria-busy") === "true") return;
  t.disabled = true; t.setAttribute?.("aria-busy", "true");
  const links = {}; for (const r of p.records) if (r.payment_id && (!r.exists || r.kind === "invoice")) links[r.row] = r.payment_id;
  let res;
  try { res = await api("/api/sql/apply", { json: { token: p.token, header_row: p.header_row, mapping: p.mapping, links, journal_id: p.journal_lines?.chosen } }); }
  catch (e) { t.disabled = false; t.removeAttribute?.("aria-busy"); throw e; }
  state.sqlPreview = null; delete state.sqlPaste[state.entity];
  const S = sqState();
  Object.assign(S, { done: sqDone(p, res), arrive: true, file: null, sel: {} });
  return render();
}
function sqlCancel() {
  state.sqlPreview = null; delete state.sqlPaste[state.entity];
  const S = sqState(); S.done = null; S.reading = null;
  sqPaint("result"); sqPaint("steps"); sqFetchBtnPaint();
  const box = $("#sqlPaste"); if (box) box.value = "";
  $("#sqlFetch")?.focus?.();
}
async function sqlDirSave() {
  const S = sqState(), box = $("#sqlDir");
  S.folderVal = box?.value || "";
  let r;
  try { r = await api("/api/settings/sql-exports-dir", { json: { sql_exports_dir: S.folderVal } }); }
  catch (e) { if (appStopped(e)) throw e; S.folderErr = e.message; sqPaint("fetch"); return $("#sqlDir")?.focus?.(); }
  state.meta.sql_exports_dir = r.sql_exports_dir; state.meta.sql_exports_default = r.default;
  Object.assign(S, { folderEdit: false, folderErr: "", fetchErr: "", folderMsg: r.default ? "Reading your Downloads folder" : "Folder saved" });
  sqPaint("fetch"); $("#sq-folder-btn")?.focus?.();
}
function sqFolder(open, fromError) {
  const S = sqState(), m = state.meta;
  Object.assign(S, { folderEdit: open, folderErr: "", folderMsg: "", folderVal: fromError ? m.sql_exports_dir || "" : m.sql_exports_default ? "" : m.sql_exports_dir || "" });
  sqPaint("fetch"); sqFetchBtnPaint();
  if (open) { $("#sq-fetch")?.scrollIntoView?.({ behavior: sqCalm() ? "auto" : "smooth", block: "start" }); $("#sqlDir")?.focus?.(); }
  else $("#sq-folder-btn")?.focus?.();
}
function sqPasteInstead() {
  const S = sqState(); S.mode = "paste"; sqPaint("bring");
  $("#sql-paste")?.scrollIntoView?.({ behavior: sqCalm() ? "auto" : "smooth", block: "start" });
  $("#sqlPaste")?.focus?.({ preventScroll: true });
}
function sqTab(k, focus) {
  const S = sqState();
  if (S.mode !== k) { S.mode = k; sqPaint("bring"); }
  if (focus) $(`#sql-tab-${k}`)?.focus?.();
}
// Create payments for all and Ignore all ask first, in place, and say what they will do.
async function sqlCreateAll() {
  const S = sqState(); S.confirmAll = true; S.confirmIgnore = false; sqPaint("entries"); $("#sq-all-yes")?.focus?.();
}
async function sqlIgnoreAll() {
  const S = sqState(); S.confirmIgnore = true; S.confirmAll = false; sqPaint("entries"); $("#sq-ign-yes")?.focus?.();
}
async function sqAsk(what) {
  const S = sqState();
  if (what === "all-no" || what === "ign-no") {
    S.confirmAll = false; S.confirmIgnore = false; sqPaint("entries");
    return $(what === "all-no" ? "#sqlCreateAll" : "#sqlIgnoreAll")?.focus?.();
  }
  // The answer is sent once: a second click while it is on its way does nothing, and the button says it is busy.
  if (S.asking) return;
  S.asking = true;
  const b = $(`#sq-${what}`);
  if (b) { b.disabled = true; b.setAttribute?.("aria-busy", "true"); }
  try {
    if (what === "all-yes") {
      const r = await api("/api/sql/entries/create-all", { json: { entity_id: state.entity } });
      toast(`Created ${r.created} payments from SQL${r.linked ? `; ${r.linked} linked to existing payments with the same SQL number` : ""}${r.left ? `; ${r.left} left for you to check (number already linked, changed in SQL?)` : ""}${r.corrections.length ? `; ${r.corrections.length} left out as probably corrections (no money moved)` : ""}; ${r.bank_lines_matched} bank lines matched${heldNote(r.held)}`);
    } else {
      const r = await api("/api/sql/entries/ignore", { json: { ids: state.sqlCorrections } });
      toast(r.ignored === 1 ? "1 entry ignored; it is listed under Ignored" : `${r.ignored} entries ignored; they are listed under Ignored`);
    }
  } catch (e) { if (appStopped(e)) throw e; toast(e.message, true); }
  finally {
    // Done or refused, the question goes: the lists are read again, so it is never left armed with an old list.
    S.asking = false; S.confirmAll = false; S.confirmIgnore = false;
    sqPaint("entries");
  }
  return render();
}
// The entry an action is on, from what the page last read.
const sqEntry = id => { const d = state.sqData; return d ? [...d.unlinked, ...(d.documents || []), ...(d.before_tracking || []), ...d.linked, ...d.ignored].find(x => x.id === id) || null : null; };
// Undo of a link: the server unlinks, and removes the payment only when it is just what Create payment made with nothing on
// it since (no bank line matched, no document); the toast says which happened.
const sqUndo = no => async () => {
  const r = await api(`/api/sql/entries/${no.id}/unlink`, { json: {} });
  toast(r.removed ? `Undone. ${no.doc} is not linked, and the payment made from it was removed.`
    : no.made ? `Undone. ${no.doc} is not linked; the payment made from it stays, because something is on it now (a matched bank line or a document).`
    : `Undone. ${no.doc} is not linked.`);
  return render();
};
async function sqlEntryLink(id) {
  const v = $(`select[data-sql-link="${id}"]`)?.value;
  if (!v) return toast("Choose a payment first.", true);
  const x = sqEntry(id), no = x?.doc_no || "The entry", pay = (state.sqData?.candidates || []).find(p => p.id === +v);
  const r = await api(`/api/sql/entries/${id}`, { json: { payment_id: +v } });
  delete sqState().sel[id];
  toast(`Linked ${no}${pay ? ` to ${pay.description}` : ""}. The voucher number is now on the payment${matchedNote(r)}.`, false,
    { undo: sqUndo({ id, doc: no, made: false }) });
  return render();
}
async function sqlEntryCreate(id) {
  const x = sqEntry(id), no = x?.doc_no || "the entry";
  const r = await api(`/api/sql/entries/${id}`, { json: { create_payment: {} } });
  toast(`Created a payment from ${no} and linked it${matchedNote(r)}.`, false,
    { undo: sqUndo({ id, doc: no, made: true }) });
  return render();
}
async function sqlEntryIgnore(id) {
  const x = sqEntry(id), no = x?.doc_no || "The entry";
  await api(`/api/sql/entries/${id}`, { json: { status: "ignored" } });
  toast(`Ignored ${no}. It is kept under Ignored, below.`, false,
    { undo: async () => { await api(`/api/sql/entries/${id}/unignore`, { json: {} }); toast(`Undone. ${no} is back under SQL entries not linked.`); return render(); } });
  return render();
}
// A lines pill or Lines button: opens the document's account lines in a row under it (or closes them).
async function sqlLinesToggle(t, no) {
  const row = t.closest("tr"), next = row?.nextElementSibling;
  const open = !!next?.classList?.contains("sql-lines-row") && next.dataset.doc === no;
  if (next?.classList?.contains("sql-lines-row")) {
    next.remove();
    for (const b of row.querySelectorAll("[data-sql-lines]")) { b.setAttribute("aria-expanded", "false"); b.querySelector(".chev")?.classList.remove("on"); }
  }
  if (open) return;
  const v = await api(`/api/ledger/doc?entity=${state.entity}&doc_no=${encodeURIComponent(no)}`);
  const tr = document.createElement("tr");
  tr.className = "sql-lines-row"; tr.dataset.doc = no; tr.id = `sq-l-${String(no).replace(/[^\w-]/g, "_")}`;
  tr.innerHTML = `<td colspan="${row.children.length}">${ledgerDocView(v)}</td>`;
  row.after(tr);
  t.setAttribute("aria-expanded", "true"); t.setAttribute("aria-controls", tr.id); t.querySelector(".chev")?.classList.add("on");
}
// A file chosen in the box or dropped on it: one that can't be an SQL export is refused here, with what to do.
function sqTakeFile(f, many) {
  const S = sqState();
  S.drag = false;
  if (many) { S.file = null; S.fileErr = "Drop one file at a time."; }
  else if (!f) { /* nothing chosen: what was chosen before stays */ }
  else if (!SQ_TYPES.test(f.name)) { S.file = null; S.fileErr = `${f.name}: Export the SQL report as Excel (.xlsx or .xls), CSV or ODS.`; }
  else if (f.size > SQ_MAX) { S.file = null; S.fileErr = `This file is too large to read (${(f.size / 1024 / 1024).toFixed(1)} MB; at most 25 MB). Export a shorter period from SQL Account.`; }
  else { S.file = f; S.fileErr = ""; }
  sqDropPaint();
}
// The box changes in place, so the file field keeps the focus.
function sqDropPaint() {
  const S = sqState(), box = $("#sql-drop");
  if (!box) return;
  box.classList.toggle?.("on", !!S.drag); box.classList.toggle?.("bad", !!S.fileErr);
  const t = box.querySelector?.(".sq-drop-t");
  if (t) t.innerHTML = S.drag ? `<b>Drop the file to choose it</b>` : `<b>Choose an SQL export</b> or drop it here`;
  const hint = $("#sql-file-hint"); if (hint) hint.textContent = sqFileHint();
  const inp = $("#sqlFile"); if (inp) { if (S.fileErr) inp.setAttribute("aria-invalid", "true"); else inp.removeAttribute("aria-invalid"); }
  const err = $("#sq-ferr"); if (err) err.innerHTML = sqFileErr();
}

/* ---------------- This page's own listeners ---------------- */
document.addEventListener("click", async ev => {
  const t = ev.target?.closest?.("button, a");
  if (!t || state.view !== "sql") return;
  const ds = t.dataset || {};
  try {
    if (ds.sqTab) return sqTab(ds.sqTab, true);
    if (ds.sqFolder) return sqFolder(!sqState().folderEdit, false);
    if (ds.sqFolderFix) return sqFolder(true, !!sqState().fetchErr);
    if (ds.sqPasteInstead) { ev.preventDefault?.(); return sqPasteInstead(); }
    if (ds.sqRefetch) return sqlFetch();
    if (ds.sqLegend || ds.sqLeft) {
      const S = sqState(), k = ds.sqLegend ? "legend" : "left";
      S[k] = !S[k]; sqPaint("result"); return $(`[data-sq-${k}]`)?.focus?.();
    }
    if (ds.sqCols) { const S = sqState(); S.cols = !S.cols; sqPaint("result"); return $("[data-sq-cols]")?.focus?.(); }
    if (ds.sqFold) {
      state.sqlOpen[ds.sqFold] = t.getAttribute?.("aria-expanded") !== "true";
      sqPaint(ds.sqFold === "own" ? "checks" : "entries"); return $(`#sq-fold-${ds.sqFold}`)?.focus?.();
    }
    if (ds.sqAsk) return await sqAsk(ds.sqAsk);
    if (ds.sqJump) return sqJump(ds.sqJump);
    if (ds.sqDoneClose) { sqState().done = null; sqPaint("result"); sqPaint("steps"); sqFetchBtnPaint(); return $("#sqlFetch")?.focus?.(); }
  } catch (e) { toast(e.message, true); }
});
document.addEventListener("change", ev => {
  const t = ev.target;
  if (!t || state.view !== "sql") return;
  const ds = t.dataset || {};
  if (t.id === "sqlFile") return sqTakeFile(t.files?.[0]);
  if (ds.sqlLink) {  // a payment picked to link: Link can be pressed now
    sqState().sel[ds.sqlLink] = t.value;
    const b = $(`[data-sql-link-go="${ds.sqlLink}"]`); if (b) b.disabled = !t.value;
    return;
  }
  if (ds.sqlRow && state.sqlPreview) {  // a payment picked in the preview: the row, the import note and the button follow
    const p = state.sqlPreview, r = p.records.find(x => x.row === +ds.sqlRow);
    if (!r) return;
    r.payment_id = t.value ? +t.value : null; r.picked = true;
    const label = $("#sq-apply-t"); if (label) label.textContent = applyLabel(p);
    const note = $("#sq-inote"); if (note) note.textContent = sqImportNote(p);
    const hint = $(`[data-sq-nopay="${ds.sqlRow}"]`); if (hint) hint.hidden = !!r.payment_id;
    if (r.kind === "payment" && !r.exists) t.classList?.toggle?.("warn", !r.payment_id);
  }
});
// Typing or pasting in the box takes its error away. A paste sets the box itself (core/listeners.js, no input event), so
// it is caught here too.
const sqPasteClear = ev => {
  if (state.view !== "sql" || ev.target?.id !== "sqlPaste" || !sqState().pasteErr) return;
  sqState().pasteErr = ""; ev.target.removeAttribute?.("aria-invalid"); ev.target.removeAttribute?.("aria-describedby"); $("#sq-paste-err")?.remove?.();
};
document.addEventListener("input", sqPasteClear);
document.addEventListener("paste", sqPasteClear);
document.addEventListener("submit", ev => {
  const id = ev.target?.id;
  if (id !== "sqlForm" && id !== "sqlPasteForm") return;
  ev.preventDefault();
  sqlRead(id === "sqlForm" ? "file" : "paste").catch(e => toast(e.message, true));
});
document.addEventListener("keydown", ev => {
  if (state.view !== "sql") return;
  const t = ev.target, ds = t?.dataset || {};
  // The two tabs: the arrow keys (wrapping), Home and End pick a tab and move the focus to it.
  if (ds.sqTab && ["ArrowRight", "ArrowLeft", "Home", "End"].includes(ev.key)) {
    ev.preventDefault();
    return sqTab(ev.key === "Home" ? "paste" : ev.key === "End" ? "file" : ds.sqTab === "paste" ? "file" : "paste", true);
  }
  if (t?.id === "sqlDir" && ev.key === "Enter") { ev.preventDefault(); return sqlDirSave().catch(e => toast(e.message, true)); }
  if (t?.id === "sqlDir" && ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); return sqFolder(false); }
  if (ev.key === "Escape" && t?.closest?.(".sq-ask")) { ev.preventDefault(); ev.stopPropagation(); return sqAsk(sqState().confirmAll ? "all-no" : "ign-no"); }
}, true);
// Drag and drop on the file box: the box shows it will take the file; a drop chooses it. Caught on the way down, so the
// drop elsewhere on the page (core/listeners.js) doesn't also say where files go.
const sqDropBox = ev => state.view === "sql" && ev.dataTransfer?.types?.includes?.("Files") && ev.target?.closest?.("#sql-drop");
document.addEventListener("dragover", ev => {
  if (!sqDropBox(ev)) return;
  ev.preventDefault(); ev.stopPropagation();
  const S = sqState(); if (!S.drag) { S.drag = true; sqDropPaint(); }
}, true);
document.addEventListener("dragleave", ev => {
  if (!sqDropBox(ev)) return;
  const box = $("#sql-drop");
  if (box && ev.relatedTarget && box.contains?.(ev.relatedTarget)) return;
  sqState().drag = false; sqDropPaint();
}, true);
document.addEventListener("drop", ev => {
  if (!sqDropBox(ev)) return;
  ev.preventDefault(); ev.stopPropagation();
  const files = [...(ev.dataTransfer.files || [])];
  sqTakeFile(files[0], files.length > 1);
}, true);
