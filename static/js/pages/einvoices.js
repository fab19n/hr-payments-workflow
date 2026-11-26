"use strict";
/* ---------------- Accounting › e-Invoices (slice 6) ----------------
   Built to design/canvas/MyInvois.dc.html, with the print notes InvoicePdf.dc.html draws beside each PDF. For both company
   kinds: a company Kept in SQL Account sees where its e-Invoices come from (the copy of SQL's MyInvois Transaction screen
   Fetch read on SQL import, as one line), then the Issued, Received and Self-billed tabs for a month (the month being
   worked, unless another is chosen here), with the Print column, All of the month (one zip of the tab's documents), the
   print settings still missing and, on Received, the e-Invoices received that SQL's books don't have. A company kept here
   reads "Submission method not decided yet" and its tabs are empty. Data: GET /api/einvoices (hrp/einvoicebook.py); each
   printable row's notes come from GET /api/invoices/<id>/check once the row is shown. Nothing here can be changed.
   What the page keeps while it is on one company and month: eiState(). */

const EI_TABS = [["issued", "Issued", "ei-tab-issued"], ["received", "Received", "ei-tab-received"], ["self-billed", "Self-billed", "ei-tab-sb"]];
const EI_STEP = 25;
// All of the month, for the whole page: one zip in flight at a time (whatever company, month or tab it was asked from), its
// request's number (an answer that isn't the latest's is ignored), and what it came to, shown on its own company, tab and month.
const EI_ZIP = { busy: false, n: 0, key: null, done: "", err: "" };
const EI_LIST = { issued: "issued", received: "received", "self-billed": "self_billed" };
// "2026-10-01 11:19:44" (or with a T) is written "1 Oct 2026, 11:19"; a day alone, "1 Oct 2026".
const eiWhen = iso => { if (!iso) return ""; const s = String(iso); return `${fmtDate(s)}${s.length > 10 ? ", " + s.slice(11, 16) : ""}`; };
const eiAmt = (n, cur) => n == null ? "—" : `${cur && cur !== "MYR" ? esc(cur) + " " : ""}${Number(n).toLocaleString("en-MY", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const eiTab = () => { const t = state.addr?.params?.tab; return EI_TABS.some(([k]) => k === t) ? t : "issued"; };
function eiState() {
  const key = `${state.entity}:${state.month}`;
  if (!state.ei || state.ei.key !== key) state.ei = { key, month: state.month, shown: EI_STEP, notes: {}, open: {}, unused: false, other: false };
  return state.ei;
}
const eiInMonth = (rows, m) => m === "all" ? rows : rows.filter(x => (x.date || "").slice(0, 7) === m);
const eiMonthWords = m => m === "all" ? "all months" : monthName(m);
const eiLink = page => `<a class="sq-linkbtn" href="${esc(menuHref(MENU_BY_PAGE[page]))}" data-menu="${esc(page)}">`;

/* ---------------- The head and the cards above the list ---------------- */
function eiHead(e) {
  const intro = e.uses_sql
    ? `${e.code}'s MyInvois e-Invoices: those it issued to customers, those suppliers sent it, and the self-billed ones it made for overseas suppliers. Each shows whether LHDN validated it and links to its MyInvois page; customer documents and self-billed invoices print as SQL Account prints them. Nothing here can be edited: it follows SQL.`
    : `${e.code}'s MyInvois e-Invoices: those it issues, those it receives and the self-billed ones it makes. ${e.code} is kept here, so they will come from its own documents, not from SQL Account.`;
  return `<div class="pg-head"><div class="pg-words"><span class="eyebrow">${esc(e.code)} · ${esc(keptLabel(e))}</span><h1 id="pg-h1" tabindex="-1">e-Invoices</h1>
    <p class="sq-lede">${esc(intro)}</p></div></div>`;
}
// A company kept here: how its e-Invoices will reach MyInvois is not decided.
function eiHereCard(e) {
  return `<section class="card ei-here" aria-labelledby="ei-here-h"><span class="sq-plate mute">${icon("clock")}</span><div class="sq-grow">
      <h2 id="ei-here-h">Submission method not decided yet</h2>
      <p class="note">${esc(e.name)} is kept here, so its e-Invoices don't come from SQL Account. How they will reach MyInvois is not decided yet, so nothing is sent to MyInvois or read from it for ${esc(e.code)}. Once Sales holds ${esc(e.code)}'s invoices and notes, they are listed here with a Print column and print from ${esc(e.code)}'s own documents.</p></div>
    ${eiLink("accounting/sales")}Open Sales${icon("arrow")}</a></section>`;
}
// The copy of MyInvois the lists come from, in one line (the fetch itself stays on SQL import); the copies the last fetch
// of this visit left out, folded.
function eiSource(e, d) {
  const S = eiState(), src = d.sources[0], c = d.counts || {}, n = (c.issued || 0) + (c.received || 0) + (c.self_billed || 0) + (c.other || 0);
  const sql = `${eiLink("accounting/sql")}Open SQL import${icon("arrow")}</a>`;
  const line = d.copy && src
    ? `<div class="ei-src">${icon("sheet")}<p>From <b>${esc(src.name)}</b>${d.sources.length > 1 ? ` (and ${plural(d.sources.length - 1, "earlier copy", "earlier copies")})` : ""}, saved ${esc(eiWhen(src.saved))}, read ${esc(eiWhen(src.read_at))} by Fetch on SQL import: ${plural(n, "e-Invoice")} (${c.issued || 0} issued, ${c.received || 0} received, ${c.self_billed || 0} self-billed${c.other ? `, ${c.other} other` : ""}).</p>${sql}</div>`
    : `<div class="ei-src">${icon("inbox")}<p><b>No copy of MyInvois read yet</b>, so the status shown is SQL's own and nothing received is known. In SQL, open the MyInvois Transaction screen, click the grid, press <b>Ctrl+A</b> then <b>Ctrl+C</b>, paste it into a new Excel workbook with its headings and save it in the exports folder under any name, then use Fetch from SQL exports on SQL import. The company's TIN must be in Setup › Companies.</p>
        <div class="ei-src-go">${sql}<button type="button" class="sq-linkbtn" data-inv-setup="1">Open Setup › Companies</button></div></div>`;
  // What the last fetch of this visit found (SQL import keeps it while the preview is open): the MyInvois copies it left out.
  const P = state.sqlPreview, left = P && P.entity_id === e.id ? (P.fetch?.files || []).filter(f => f.status !== "read" && /MyInvois/.test(f.reason || "")) : [];
  const when = P ? sqTitle(P.filename).replace(/^SQL (?:exports|reports) fetched /, "") : "";
  const unused = left.length ? `<div class="ei-unused"><button type="button" class="sq-quiet" id="ei-unused-b" data-ei-unused="1" aria-expanded="${S.unused}" aria-controls="ei-unused">
      <span class="chev${S.unused ? " on" : ""}" aria-hidden="true">${icon("chevronRight")}</span>${icon("alert")}The fetch${when && !/\./.test(when) ? ` of ${esc(when)}` : ""} left out ${plural(left.length, "MyInvois copy", "MyInvois copies")}</button>
      ${S.unused ? `<ul id="ei-unused">${left.map(f => { const st = SQ_STATUS[f.status] || ["Not used", "warn", "alert"];
        return `<li><div><b>${esc(f.name)}</b>: ${esc(f.reason)}</div><span class="pill ${st[1]}">${icon(st[2])}${esc(st[0])}</span>${/Setup › Companies/.test(f.reason) ? `<button type="button" class="sq-linkbtn" data-inv-setup="1">Open Setup › Companies</button>` : ""}</li>`; }).join("")}</ul>` : ""}</div>` : "";
  const oth = d.other || [];
  const other = oth.length ? `<div class="ei-unused ei-other"><button type="button" class="sq-quiet" id="ei-other-b" data-ei-other="1" aria-expanded="${!!S.other}" aria-controls="ei-other">
      <span class="chev${S.other ? " on" : ""}" aria-hidden="true">${icon("chevronRight")}</span>${icon("inbox")}${plural(oth.length, "other e-Invoice")} in the copy, neither issued by ${esc(e.code)} nor sent to it</button>
      ${S.other ? `<div class="tbl-wrap sq-tw" id="ei-other" role="region" aria-label="Other e-Invoices in the copy" tabindex="0"><table class="sq-tbl ei-tbl"><caption class="sr-only">Other e-Invoices in the copy</caption>
        <thead><tr><th scope="col">Issued</th><th scope="col">Doc no.</th><th scope="col">Supplier</th><th scope="col">Buyer</th><th scope="col" class="num">Amount</th><th scope="col">Status</th><th scope="col">MyInvois</th></tr></thead><tbody>
        ${oth.map(r => `<tr><td class="nowrap">${fmtDate(r.date)}</td><td class="mono">${esc(r.doc_no)}${r.type ? `<div class="note small">${esc(r.type)}</div>` : ""}</td>
          <td>${esc(r.supplier)}${r.supplier_tin ? `<div class="note small">${esc(r.supplier_tin)}</div>` : ""}</td><td>${esc(r.buyer)}${r.buyer_tin ? `<div class="note small">${esc(r.buyer_tin)}</div>` : ""}</td>
          <td class="num">${esc(r.currency)} ${eiAmt(r.amount)}</td><td><span class="pill ${r.status === "Valid" ? "ok" : "warn"}">${esc(r.status)}</span></td>
          <td class="mono">${r.link ? `<a href="${esc(r.link)}" target="_blank" rel="noopener noreferrer" aria-label="${esc(`Open ${r.doc_no} on MyInvois, opens in a new tab`)}">${esc(r.uuid)} ↗</a>` : esc(r.uuid)}</td></tr>`).join("")}
        </tbody></table></div>` : ""}</div>` : "";
  return `<section class="card sq-card ei-source" aria-label="Where these e-Invoices come from">${line}${other}${unused}</section>`;
}

/* ---------------- The list: tabs, month, Excel, then the tab's panel ---------------- */
function eiMonths(d) {
  const S = eiState(), all = d ? [...d.issued, ...d.received, ...d.self_billed] : [];
  const ms = [...new Set([...all.map(x => (x.date || "").slice(0, 7)).filter(Boolean), state.month])].sort().reverse();
  const allLabel = !d ? "All months" : d.copy && d.span ? `All months in the copy (${shortDate(d.span[0])} to ${shortDate(d.span[1])})` : "All months fetched";
  return [...ms.map(m => [m, monthName(m)]), ["all", allLabel]].map(([v, l]) => `<option value="${esc(v)}"${v === S.month ? " selected" : ""}>${esc(l)}</option>`).join("");
}
const eiRows = (d, tab) => d ? eiInMonth(d[EI_LIST[tab]], eiState().month) : [];
function eiTabsHtml(d) {
  const cur = eiTab();
  return EI_TABS.map(([k, label, id]) => { const n = eiRows(d, k).length, on = k === cur;
    return `<button type="button" role="tab" class="sq-tab ei-tab" id="${id}" data-ei-tab="${k}" aria-selected="${on}" aria-controls="ei-panel" aria-label="${esc(label)}, ${n}" tabindex="${on ? 0 : -1}">${esc(label)}<span class="ei-n">${n}</span></button>`; }).join("");
}
const eiListHead = () => `${EI_TABS.find(t => t[0] === eiTab())[1]} e-Invoices, ${eiMonthWords(eiState().month)}`;
const eiExcel = () => `/api/export/einvoices.xlsx?entity_id=${state.entity}${eiState().month === "all" ? "" : `&month=${eiState().month}`}`;
function eiList(d) {
  const tab = eiTab(), id = EI_TABS.find(t => t[0] === tab)[2];
  return `<section class="card sq-card ei-list" aria-labelledby="ei-list-h"><h2 id="ei-list-h" class="sr-only">${esc(eiListHead())}</h2>
    <div class="ei-bar"><div role="tablist" class="sq-tabs ei-tabs" id="ei-tabs" aria-label="Which e-Invoices">${eiTabsHtml(d)}</div>
      <div class="ei-tools"><label class="ei-month"><span>Month</span><select id="ei-month" data-ei-month="1">${eiMonths(d)}</select></label>
        ${d ? `<a class="ghost small" id="ei-xl" href="${esc(eiExcel())}" download title="These e-Invoices as an Excel file, for the month chosen">${icon("download")}Excel</a>` : ""}</div></div>
    <div role="tabpanel" id="ei-panel" aria-labelledby="${id}">${eiPanel(d)}</div></section>`;
}

/* ---------------- The panel ---------------- */
// Print, above the Issued and Self-billed tables: All of the month (one zip), and the print settings still missing.
function eiZipInfo(d) {
  const S = eiState(), tab = eiTab(), e = ent(), self = tab === "self-billed";
  // How many documents the zip holds, as the server counts them for the zip itself; else the documents listed that print.
  const m = S.month, counted = d?.print?.counts?.[self ? "self_billed" : "customer"]?.[m];
  const n = counted != null ? counted : new Set(eiRows(d, tab).filter(x => x.print_kind && x.id).map(x => x.id)).size;
  const file = `${e.code} ${self ? "Self-billed invoices" : "Invoices"} ${m}.zip`;
  const kinds = self ? (n === 1 ? "self-billed invoice" : "self-billed invoices") : (n === 1 ? "document" : "invoices, debit and credit notes");
  return { can: m !== "all" && n > 0, n, file, key: `${state.entity}:${tab}:${m}`, what: `${file}: the ${n} ${kinds} of ${eiMonthWords(m)}, one PDF each`,
    url: `/api/invoices/month.zip?entity=${state.entity}&entity_id=${state.entity}&month=${m}&kind=${self ? "self_billed" : "customer"}` };
}
function eiPrintInner(d) {
  const S = eiState(), z = eiZipInfo(d), Z = EI_ZIP.key === z.key ? EI_ZIP : {}, p = d.print;
  const elsewhere = EI_ZIP.busy && EI_ZIP.key !== z.key;  // a zip of another company, tab or month is still being made: one at a time
  const zip = z.can
    ? `<button type="button" class="ghost small" id="ei-zip" data-ei-zip="1" aria-describedby="ei-zip-what"${Z.busy ? ' aria-busy="true" aria-disabled="true"' : elsewhere ? ' aria-disabled="true" title="Another zip is being made. Wait for it to be saved."' : ""}>${Z.busy ? `<span class="spin sq-spin" aria-hidden="true"></span>Making the zip…` : `${icon("download")}All of the month`}</button><span class="note" id="ei-zip-what">${esc(z.what)}</span>`
    : `<span class="note">${S.month === "all" ? "Choose a month to print all of it as one zip." : `Nothing to print for ${esc(eiMonthWords(S.month))}.`}</span>`;
  const done = Z.done && !Z.busy ? `<span class="ei-done">${icon("check")}Saved ${esc(Z.done)}</span>` : "";
  const bad = Z.err ? `<span class="note warn" role="alert">${esc(Z.err)}</span>` : "";
  const missing = p.missing.length ? `<div class="ei-set">${icon("alert")}<div><b>Print settings:</b> invoices print without what is missing.<ul>${p.missing.map(m => `<li>${esc(m)}</li>`).join("")}</ul></div>
      <button type="button" class="sq-linkbtn" data-inv-setup="1">Open Setup › Companies</button></div>` : "";
  return `<div class="ei-print-row"><span class="sq-ic">${icon("printer")}</span><b>Print</b>${zip}${done}${bad}</div>${missing}${fontNote(p.fonts)}${tooLongNote(p.too_long)}`;
}
// The status SQL's document carries (a credit note or refund that takes it back says so), with its MyInvois page.
function eiPill(x) {
  if (!x.status && !x.taken_back_by) return `<span class="muted">—</span>`;
  const ok = (x.status || "").startsWith("Validated") && !x.taken_back_by;
  const text = x.taken_back_by ? `Cancelled by ${x.taken_back_by}` : x.status;
  return `<span class="pill ${ok ? "ok" : "warn"}">${icon(ok ? "verified" : x.taken_back_by ? "alert" : "clock")}${esc(text)}</span>`
    + (x.link ? `<div><a href="${esc(x.link)}" target="_blank" rel="noopener noreferrer" aria-label="${esc(`Open ${x.doc_no} on MyInvois, opens in a new tab`)}">MyInvois ↗</a></div>` : "");
}
// The Print column: the PDF (in a new tab), and beside it the print note the check keeps for the document.
const eiUnlink = x => x.id && x.payment_id ? `<button type="button" class="ghost small" data-sql-unlink="${+x.id}" aria-label="${esc(`Unlink ${x.doc_no} from its payment`)}">Unlink</button>` : "";
function eiPdf(x) {
  if (!x.print_kind || !x.id) return eiUnlink(x) || `<span class="muted">—</span>`;
  const what = x.what, label = what === "self-billed invoice" ? "Invoice PDF" : `${what[0].toUpperCase()}${what.slice(1)} PDF`;
  return `<div class="ei-pdf"><a class="ghost small" href="/api/invoices/${+x.id}.pdf?entity_id=${state.entity}" target="_blank" rel="noopener" title="${esc(`The ${what}, laid out as SQL Account prints it`)}" aria-label="${esc(`${label} of ${x.doc_no}, opens in a new tab`)}">${icon("document")}${esc(label)}</a>
    <span id="ei-pn-${+x.id}">${eiNote(x.id)}</span>${eiUnlink(x)}</div>`;
}
// The note marker: what the print check says of the document (or why it can't be printed), on hover and when opened.
function eiNote(id) {
  const S = eiState(), r = S.notes[id];
  if (!r || (!r.err && !r.notes.length)) return "";
  const list = r.err ? [r.err] : r.notes, open = !!S.open[id];
  const label = r.err ? "Not printed" : plural(list.length, "print note");
  return `<button type="button" class="ei-pn-b${r.err ? " bad" : ""}" id="ei-pn-b-${+id}" data-ei-note="${+id}" aria-expanded="${open}" aria-controls="ei-pn-list-${+id}" title="${esc(list.join("\n"))}">${icon("alert")}${esc(label)}</button>`
    + (open ? `<ul class="ei-pn-list" id="ei-pn-list-${+id}">${list.map(t => `<li>${esc(t)}</li>`).join("")}</ul>` : "");
}
function eiDocsTable(rows, tab, caption) {
  const self = tab === "self-billed";
  return `<div class="tbl-wrap sq-tw" role="region" aria-label="${esc(caption)}" tabindex="0"><table class="sq-tbl ei-tbl"><caption class="sr-only">${esc(caption)}</caption>
    <thead><tr><th scope="col">Doc no.</th><th scope="col">Date</th><th scope="col">Description</th><th scope="col" class="num">${self ? "Amount" : "Amount (RM)"}</th><th scope="col">Status</th><th scope="col">MyInvois</th><th scope="col">Print</th></tr></thead><tbody>
    ${rows.map((x, i) => { const m = x.myinvois, p = x.party;
      return `<tr id="ei-row-${i}" tabindex="-1"><td class="mono sq-no">${esc(x.doc_no)}</td><td class="nowrap">${shortDate(x.date)}</td>
        <td>${esc(x.description)}${p.name ? `<div class="note small">${esc(p.label)}: ${esc(p.name)}${p.tin ? ` (${esc(p.tin)})` : ""}</div>` : ""}${x.paid_as ? `<div class="note small">Paid as ${esc(money(x.paid_as.amount))} by ${esc(x.paid_as.by)}</div>` : ""}${(x.also || []).length ? `<div class="note small">Also in SQL: ${esc(x.also.map(a => a.doc_no).join(", "))}</div>` : ""}</td>
        <td class="num">${self ? `${esc(x.currency || "MYR")} ${eiAmt(x.amount)}` : eiAmt(x.amount, x.currency)}</td><td>${eiPill(x)}</td>
        <td>${m ? `<span class="mono ei-uuid">${esc(m.uuid)}</span><div class="note small">${esc([m.type, m.status].filter(Boolean).join(" · "))}${m.validated_at ? ` · validated ${esc(eiWhen(m.validated_at))}` : ""}</div>` : `<span class="muted">—</span>`}</td>
        <td id="ei-pc-${i}">${eiPdf(x)}</td></tr>`; }).join("")}</tbody></table></div>`;
}
const EI_MATCH_TIP = { "By amount": "A likely match, by amount only: check it", "By a line's amount": "A likely match, by one line's amount only: check it", "Paid together": "One voucher in SQL paid these together" };
function eiRecvTable(rows, caption) {
  return `<div class="tbl-wrap sq-tw" role="region" aria-label="${esc(caption)}" tabindex="0"><table class="sq-tbl ei-tbl"><caption class="sr-only">${esc(caption)}</caption>
    <thead><tr><th scope="col">Issued</th><th scope="col">From</th><th scope="col">Their number</th><th scope="col" class="num">Amount (RM)</th><th scope="col">Status</th><th scope="col">MyInvois</th><th scope="col">In SQL</th></tr></thead><tbody>
    ${rows.map((r, i) => `<tr id="ei-row-${i}" tabindex="-1"><td class="nowrap">${fmtDate(r.date)}</td><td>${esc(r.party)}${r.code ? `<div class="note small">Code ${esc(r.code)}</div>` : ""}</td>
      <td class="mono">${esc(r.their || "—")}</td><td class="num">${eiAmt(r.amount, r.currency)}</td>
      <td>${r.sql_only ? eiPill({ ...r, doc_no: r.in_sql, link: null }) : `<span class="pill ${r.status === "Valid" ? "ok" : "warn"}">${icon(r.status === "Valid" ? "verified" : "clock")}${esc(r.status)}</span>`}${r.validated_at ? `<div class="note small">Validated ${esc(eiWhen(r.validated_at))}</div>` : ""}</td>
      <td class="mono">${!r.uuid ? `<span class="muted">—</span>` : r.link ? `<a href="${esc(r.link)}" target="_blank" rel="noopener noreferrer" title="Open it on MyInvois" aria-label="${esc(`Open the e-Invoice from ${r.party}${r.their ? " " + r.their : ""} on MyInvois, opens in a new tab`)}">${esc(r.uuid)} ↗</a>` : esc(r.uuid)}</td>
      <td>${r.in_sql ? `<b class="mono">${esc([r.in_sql, ...(r.also || []).map(a => a.doc_no)].join(", "))}</b>${r.matched_by ? ` <span class="pill grey" title="${esc(EI_MATCH_TIP[r.matched_by] || "")}">${esc(r.matched_by)}</span>` : ""}${r.sql_only ? `<div class="note small">From SQL: no copy of MyInvois has it yet</div>` : ""}${eiUnlink({ ...r, doc_no: r.in_sql })}` : `<span class="pill warn">${icon("alert")}Not found</span>`}</td></tr>`).join("")}
    </tbody></table></div>`;
}
// The valid e-Invoices received that none of SQL's documents has: listed whatever month is chosen.
function eiUnbooked(d) {
  const u = d.unmatched;
  return `<div class="sq-sub"><div class="sq-grow"><h3>e-Invoices received but not found in SQL's books${u.length ? ` (${u.length})` : ""}</h3>
      <span class="note">Valid e-Invoices issued to the company${d.since ? ` from ${esc(monthName(d.since))}` : ""} that no supplier invoice or payment voucher in SQL has, by the supplier's document number, its TIN and amount, or its amount alone (a whole voucher, or one line of a claim, dated near it). Check each one: it may still have to be entered in SQL. Listed whatever month is chosen.</span></div></div>
    ${u.length ? `<div class="tbl-wrap sq-tw"><table class="sq-tbl"><caption class="sr-only">e-Invoices received but not found in SQL's books</caption><thead><tr><th scope="col">Doc no.</th><th scope="col">Supplier</th><th scope="col">Supplier TIN</th><th scope="col">Issued</th><th scope="col" class="num">Total</th></tr></thead><tbody>
      ${u.map(r => `<tr><td class="mono sq-no">${esc(r.doc_no)}</td><td>${esc(r.supplier)}</td><td class="mono">${esc(r.tin)}</td><td class="nowrap">${fmtDate(r.date)}</td><td class="num">${eiAmt(r.amount, r.currency)}</td></tr>`).join("")}</tbody></table></div>`
      : sqNone("check", "ok", "None: every valid e-Invoice received is in SQL's books.")}`;
}
function eiEmptyText(d, tab) {
  const e = ent(), m = eiMonthWords(eiState().month);
  if (!e.uses_sql) return { issued: `No e-Invoices for ${e.code} yet. Its invoices and notes will be listed here once Sales holds them.`, received: `Nothing received is known for ${e.code}: how ${e.code}'s e-Invoices reach MyInvois is not decided yet.`, "self-billed": `No self-billed e-Invoices for ${e.code} yet.` }[tab];
  if (!d.copy) return { issued: `No SQL document with an e-Invoice in ${m}.`, received: `No copy of MyInvois read yet, so the e-Invoices other companies sent ${e.code} aren't known here.`, "self-billed": "None known yet: a self-billed e-Invoice shows once a copy of MyInvois is read." }[tab];
  return { issued: `No e-Invoice issued in ${m}.`, received: `No e-Invoice received in ${m}.`, "self-billed": `No self-billed e-Invoice in ${m}. They are made for overseas suppliers and claims paid abroad.` }[tab];
}
function eiPanel(d) {
  const S = eiState(), tab = eiTab(), e = ent(), all = eiRows(d, tab), shown = slice(all, S.shown);
  const label = EI_TABS.find(t => t[0] === tab)[1], many = all.length > EI_STEP;
  const caption = `${label} e-Invoices, ${eiMonthWords(S.month)}${many ? `, ${shown.length} of ${all.length} shown` : ""}`;
  const print = e.uses_sql && d && d.print && tab !== "received" ? `<div class="sq-print ei-print" id="ei-print" role="group" aria-label="Print">${eiPrintInner(d)}</div>` : "";
  const body = !all.length ? sqNone("inbox", "mute", eiEmptyText(d, tab)) : tab === "received" ? eiRecvTable(shown, caption) : eiDocsTable(shown, tab, caption);
  const more = many ? manyRows({ shown: shown.length, total: all.length, step: EI_STEP, what: "e-Invoices", attr: "data-ei-more" }) : "";
  return print + body + more + (e.uses_sql && d && d.copy && tab === "received" ? eiUnbooked(d) : "");
}

/* ---------------- The page ---------------- */
async function viewEinvoices(main) { return pageDraw("main", page => einvoicesDraw(page, main)); }
async function einvoicesDraw(page, main) {
  const e = ent(), S = eiState();
  S.notes = {}; S.open = {};  // read again each time the page is drawn: a fetch may have changed them
  if (!EI_ZIP.busy) Object.assign(EI_ZIP, { key: null, done: "", err: "" });  // a zip being made stays so: its answer is still awaited
  if (!e.uses_sql) { state.eiData = null; main.innerHTML = `<div class="sq ei" id="ei">${eiHead(e)}${eiHereCard(e)}${eiList(null)}<div class="sr-only" role="status" id="ei-say"></div></div>`; return; }
  let d;
  try { d = await page.read(api(`/api/einvoices?entity=${state.entity}`)); }
  catch (err) {
    page.check();
    if (appStopped(err) || page.saved) throw err;  // reading back a kept change: render() says it was saved
    state.eiData = null;
    main.innerHTML = `<div class="sq ei" id="ei">${eiHead(e)}${errorState({ title: "Couldn't load the e-Invoices", body: err.message })}</div>`;
    return;
  }
  state.eiData = d;
  const empty = !d.copy && !d.issued.length && !d.received.length && !d.self_billed.length;
  main.innerHTML = `<div class="sq ei" id="ei">${eiHead(e)}${empty
    ? emptyState({ glyph: "verified", title: "No e-Invoices yet", body: `Nothing has been fetched from SQL Account for ${e.code} yet. Fetch SQL's Customer Invoice listing and a copy of its MyInvois Transaction screen on SQL import, and ${e.code}'s e-Invoices show here.`,
      action: { label: "Open SQL import", attr: "data-menu", value: "accounting/sql", glyph: "database" } })
    : eiSource(e, d) + eiList(d)}<div class="sr-only" role="status" id="ei-say"></div></div>`;
  eiChecks();
}
const eiSay = text => { const s = $("#ei-say"); if (s) s.textContent = text; };
// The list after a tab, month or Show more: the tabs (their counts), the hidden heading, the Excel link and the panel.
function eiPaint() {
  const d = state.eiData, tabs = $("#ei-tabs"), panel = $("#ei-panel"), h = $("#ei-list-h"), xl = $("#ei-xl");
  if (tabs) tabs.innerHTML = eiTabsHtml(d);
  if (h) h.textContent = eiListHead();
  if (xl) xl.setAttribute("href", eiExcel());
  if (panel) { panel.innerHTML = eiPanel(d); panel.setAttribute?.("aria-labelledby", EI_TABS.find(t => t[0] === eiTab())[2]); }
  eiChecks();
}
function eiPick(k, focus) {
  if (state.view !== "einvoices" || !EI_TABS.some(t => t[0] === k)) return;
  const p = { ...(state.addr.params || {}) };
  if (k === "issued") delete p.tab; else p.tab = k;
  state.addr.params = p;
  const S = eiState(); S.shown = EI_STEP;
  syncAddr(); eiPaint();
  eiSay(`${EI_TABS.find(t => t[0] === k)[1]} e-Invoices shown.`);
  if (focus) $(`#${EI_TABS.find(t => t[0] === k)[2]}`)?.focus?.();
}
function eiMonth(v) {
  const S = eiState();
  S.month = v === "all" || MONTH_RE.test(v || "") ? v : state.month; S.shown = EI_STEP;
  eiPaint(); eiSay(`${S.month === "all" ? "All months" : monthName(S.month)} shown.`);
}
function eiMore() {
  const S = eiState(), at = Math.min(S.shown, eiRows(state.eiData, eiTab()).length);
  S.shown += EI_STEP; eiPaint();
  $(`#ei-row-${at}`)?.focus?.();
}
// The print check of each printable document shown, read once per visit, a few at a time; its marker is drawn beside its PDF. A draw of the
// page: once another page (or this one again, which reads the checks afresh) is asked for, its answers are dropped.
function eiChecks() { return pageDraw(null, eiChecksDraw); }
async function eiChecksDraw(page) {
  const d = state.eiData, tab = eiTab();
  if (!d || tab === "received") return;
  const S = eiState(), rows = slice(eiRows(d, tab), S.shown).map((x, i) => ({ x, i })).filter(r => r.x.print_kind && r.x.id && !(r.x.id in S.notes));
  for (const r of rows) S.notes[r.x.id] = null;
  const paint = id => { const at = $(`#ei-pn-${+id}`); if (at) at.innerHTML = eiNote(id); };
  const one = async ({ x }) => {
    const note = await page.read(api(`/api/invoices/${+x.id}/check`).then(c => ({ notes: c.notes || [] }), err => ({ notes: [], err: err.message })));
    S.notes[x.id] = note;
    if (state.ei === S) paint(x.id);
  };
  for (let k = 0; k < rows.length; k += 3) await Promise.all(rows.slice(k, k + 3).map(one));
}
// The page's message in the panel's print bar; the zip button keeps the focus while it is made.
function eiPaintPrint() { const p = $("#ei-print"); if (p && state.eiData?.print) p.innerHTML = eiPrintInner(state.eiData); }
// All of the month: the zip is read here and saved under its name, so the button can say it is being made and then that
// it was saved; a month the server refuses says why in place.
async function eiZip() {
  const z = eiZipInfo(state.eiData);
  if (!z.can || EI_ZIP.busy) return;  // one zip at a time, whichever company, tab or month it was asked from
  const n = ++EI_ZIP.n, mine = () => EI_ZIP.n === n;
  Object.assign(EI_ZIP, { busy: true, key: z.key, done: "", err: "" }); eiPaintPrint(); eiSay(`Making ${z.file}…`); $("#ei-zip")?.focus?.();
  try {
    const r = await fetch(z.url);
    if (!r.ok) {
      const t = r.text ? await r.text() : "", m = /<p>([\s\S]*?)<\/p>/.exec(t || "");
      throw new Error(m ? m[1].replace(/&#x27;|&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&") : `The zip couldn't be made (${r.status}).`);
    }
    eiSave(await r.blob(), z.file);
    if (mine()) { Object.assign(EI_ZIP, { busy: false, done: z.file }); if (eiZipInfo(state.eiData).key === z.key) eiSay(`Saved ${z.file}.`); }
  } catch (err) { if (mine()) Object.assign(EI_ZIP, { busy: false, err: appStopped(err) ? "HR Payments isn't running, so the zip couldn't be made. Start it again, then try again." : err.message }); }
  if (!mine() || state.view !== "einvoices") return;
  eiPaintPrint();
  if (eiZipInfo(state.eiData).key === z.key) $("#ei-zip")?.focus?.();
}
function eiSave(blob, name) {
  if (typeof URL === "undefined" || !URL.createObjectURL || typeof document.createElement !== "function" || !document.body) return;
  const a = document.createElement("a"), href = URL.createObjectURL(blob);
  a.href = href; a.download = name; a.hidden = true;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 2000);
}

/* ---------------- This page's own listeners ---------------- */
document.addEventListener("click", async ev => {
  const t = ev.target?.closest?.("button, a");
  if (!t || state.view !== "einvoices") return;
  const ds = t.dataset || {};
  try {
    if (ds.eiTab) return eiPick(ds.eiTab, true);
    if (ds.eiMore) return eiMore();
    if (ds.eiZip) return await eiZip();
    if (ds.eiNote) { const S = eiState(); S.open[ds.eiNote] = !S.open[ds.eiNote]; const at = $(`#ei-pn-${+ds.eiNote}`); if (at) at.innerHTML = eiNote(+ds.eiNote); return $(`#ei-pn-b-${+ds.eiNote}`)?.focus?.(); }
    if (ds.eiOther) { const S = eiState(); S.other = !S.other; const box = $(".ei-source"); if (box && state.eiData) box.outerHTML = eiSource(ent(), state.eiData); return $("#ei-other-b")?.focus?.(); }
    if (ds.eiUnused) { const S = eiState(); S.unused = !S.unused; const box = $(".ei-source"); if (box && state.eiData) box.outerHTML = eiSource(ent(), state.eiData); return $("#ei-unused-b")?.focus?.(); }
  } catch (e) { toast(e.message, true); }
});
document.addEventListener("change", ev => {
  if (state.view !== "einvoices" || !ev.target?.dataset?.eiMonth) return;
  eiMonth(ev.target.value);
});
document.addEventListener("keydown", ev => {
  if (state.view !== "einvoices") return;
  const t = ev.target, ds = t?.dataset || {};
  // The three tabs: the arrow keys (wrapping), Home and End pick a tab and move the focus to it.
  if (ds.eiTab && ["ArrowRight", "ArrowLeft", "Home", "End"].includes(ev.key)) {
    ev.preventDefault();
    const i = EI_TABS.findIndex(x => x[0] === ds.eiTab), n = EI_TABS.length;
    const j = ev.key === "Home" ? 0 : ev.key === "End" ? n - 1 : ev.key === "ArrowRight" ? (i + 1) % n : (i + n - 1) % n;
    return eiPick(EI_TABS[j][0], true);
  }
  // Escape closes an open print note (the focus stays on its marker) before anything else takes it.
  if (ev.key === "Escape" && ds.eiNote && eiState().open[ds.eiNote]) {
    ev.preventDefault(); ev.stopPropagation();
    const S = eiState(); S.open[ds.eiNote] = false; const at = $(`#ei-pn-${+ds.eiNote}`); if (at) at.innerHTML = eiNote(+ds.eiNote);
    return $(`#ei-pn-b-${+ds.eiNote}`)?.focus?.();
  }
}, true);
