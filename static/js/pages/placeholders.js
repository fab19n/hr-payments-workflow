"use strict";
/* ---------------- Coming soon pages and the Kept here placeholders (step 0e) ----------------
   comingSoon(main, { title, glyph, body }) is the one function for a page that is not built yet (Staff, Leave, Claims and
   advances, Approvals, To pay, and e-Invoices for a company kept here): the States pattern, one sentence about what the page
   will do, no date. keptHerePage(kind) is design/canvas/AccountingKeptHere.dc.html for Sales, Purchases, Journals and Period
   close: what will be there, how it connects, the rules every document follows. A company Kept in SQL Account has no use for
   those four (PAGE_RULES in core/states.js gives it the "isn't used" card). */
function comingSoon(main, { title, glyph, body }) {
  main.innerHTML = emptyState({ glyph, tone: "brand", title: `${title} is coming soon`, body,
    action: { label: "Open the Overview", attr: "data-view", value: "overview", ghost: true } });
}
const viewStaff = async main => comingSoon(main, { title: "Staff", glyph: "staff", body: "Each company's people and their records, with the calendar and reminders for birthdays, probation and permits." });
const viewLeave = async main => comingSoon(main, { title: "Leave", glyph: "leave", body: "Leave balances, requests and the year's leave, kept for each person." });
const viewClaims = async main => comingSoon(main, { title: "Claims and advances", glyph: "claim", body: "Staff claims and salary advances, from the request to the payment." });
const viewApprovals = async main => comingSoon(main, { title: "Approvals", glyph: "approval", body: "The forms that wait for a signed approval before a payment is made." });
const viewToPay = async main => comingSoon(main, { title: "To pay", glyph: "toPay", body: "What is approved and waiting to be paid, in one list." });

// e-Invoices: today's SQL import page, brought to its MyInvois part; a company kept here has no e-Invoices of its own yet.
async function viewEinvoices(main) {
  if (!ent()?.uses_sql) return comingSoon(main, { title: "e-Invoices", glyph: "verified", body: "Each invoice issued from here, with its MyInvois record and whether LHDN has validated it." });
  await viewSql(main);
  const at = state.landAt;
  state.landAt = null;  // brought into view once, when the address is opened; a redraw after a change stays where it is
  if (at) $("#" + at)?.scrollIntoView?.({ block: "start" });
}

const KEPT_HERE = {
  sales: { title: "Sales", intro: "Everything a Kept here company sells: invoices out, the notes that correct them, and the money that comes in against them.",
    items: [["receipt", "Customer invoices", "Raised here, posted and numbered when recorded, so customer ageing is right."],
      ["document", "Debit notes", "Extra charges on an invoice already sent."],
      ["undo", "Credit notes", "The way to correct a posted invoice. Each one must name the original invoice."],
      ["coins", "Receipts (OR series)", "Money in from a customer, knocked off to the invoices it pays. Add payment opens a receipt here when money in comes from a customer."]],
    links: [["accounting/parties", "Customers and suppliers", "who owes what, with ageing, from these invoices."],
      ["payments/register", "Payments register", "money in is counted apart, as it is today."],
      ["accounting/einvoices", "e-Invoices", "issued invoices link to their MyInvois record."]] },
  purchases: { title: "Purchases", intro: "Everything a Kept here company is billed: supplier invoices, the notes that correct them, and the payments made against them.",
    items: [["inbox", "Supplier invoices (PI series)", "A supplier bill's request is a supplier invoice here, posted when recorded. The approval covers that invoice."],
      ["document", "Debit and credit notes", "Corrections to a posted supplier invoice."],
      ["payment", "Payments", "Made from Payments. Paying posts a payment voucher and knocks the invoice off."],
      ["link", "Knock-off", "Each payment is matched to the invoice it pays, so a bill approved but not yet paid at month end is still in the books."]],
    links: [["payments/approvals", "Approvals", "the form that approves a supplier invoice."],
      ["payments/to-pay", "To pay", "approved supplier invoices wait here until they are paid."],
      ["accounting/parties", "Customers and suppliers", "supplier ageing and the Suppliers due card."]] },
  journals: { title: "Journals", intro: "The entries that do not come from an invoice or a payment: adjustments, opening balances and reversals.",
    items: [["sheet", "Journal vouchers (JV)", "A dated entry with balanced debit and credit lines, numbered when posted."],
      ["books", "Opening balances", "The balances a company starts with when it begins to be kept here."],
      ["undo", "Reversals", "A posted journal is never edited. A reversal cancels it and keeps its number."]],
    links: [["accounting/books", "Books", "each journal line opens from its account in the general ledger, and the trial balance includes every posted journal."],
      ["admin/audit-pack", "Audit pack", "its gap check covers the journal series."]] },
  close: { title: "Period close", intro: "Where a month or a year is closed so that what was reported cannot move afterwards.",
    items: [["lock", "Month locks", "A locked month cannot be changed, and posting into it is refused."],
      ["calendar", "Year-end close", "Closes the financial year and carries the balances forward."],
      ["search", "Numbering gap check", "Looks for a missing number in each series. A cancelled document keeps its number, so it is not a gap."]],
    links: [["accounting/bank", "Bank and reconciliation", "a signed-off month is locked; reopening it is logged."],
      ["payments/checklist", "Monthly checklist", "Mark month as filed sits there."]] },
};
const KEPT_HERE_RULES = ["Numbers restart every month, one series per document type per company.",
  "A document is numbered when it is posted, and the number is never edited or reused.", "A cancelled document keeps its number.",
  "A posted document is corrected by a credit note or a reversal, never edited.", "Nothing on these pages relies on SQL Account data."];

function keptHerePage(kind) {
  const P = KEPT_HERE[kind], e = ent();
  if (!P || !e) return "";
  const link = ([page, label, text]) => `<li><a href="${esc(menuHref(MENU_BY_PAGE[page]))}" data-menu="${esc(page)}">${esc(label)}</a>: ${esc(text)}</li>`;
  return `<div class="kh">
    <div class="kh-head"><span class="row"><span class="eyebrow">Accounting</span><span class="chip">${icon("books")}${esc(e.code)} · Kept here</span></span>
      <h1 id="khTitle" tabindex="-1">${esc(P.title)}</h1><p class="note">${esc(P.intro)}</p></div>
    <div class="banner info" role="note">${icon("clock")}<span><b>${esc(P.title)} is not built yet.</b> This page is a placeholder. It holds the place in the menu and lists what will be here. Nothing on it can be entered or changed yet.</span></div>
    <div class="kh-grid">
      <section class="card" aria-labelledby="khWill"><h2 id="khWill">What will be here</h2>
        <ul class="kh-items">${P.items.map(([g, t, x]) => `<li><span class="plate brand">${icon(g)}</span><div><b>${esc(t)}</b><div class="note">${esc(x)}</div></div></li>`).join("")}</ul></section>
      <div class="kh-side">
        <section class="card" aria-labelledby="khLinks"><h2 id="khLinks">How it connects</h2><ul class="kh-links">${P.links.map(link).join("")}</ul></section>
        <section class="card" aria-labelledby="khRules"><h2 id="khRules">Rules every document here follows</h2><ul class="kh-links">${KEPT_HERE_RULES.map(t => `<li>${esc(t)}</li>`).join("")}</ul></section>
      </div>
    </div></div>`;
}
const keptHereView = kind => async main => { main.innerHTML = keptHerePage(kind); };
const viewSales = keptHereView("sales"), viewPurchases = keptHereView("purchases"), viewJournals = keptHereView("journals"), viewPeriodClose = keptHereView("close");
