"use strict";
/* ---------------- Overview ----------------
   design/canvas/Main.dc.html (DarkOverview.dc.html in the dark theme; card reference OverviewCards.dc.html), build plan
   section 4.4. The top part: the audit trail notice (pages/trail.js puts it first), the date, the month's heading with Open
   budget and Add a payment, the rollover banner, Next up with Go (core/next.js) and the older months still open, and
   Recent activity. Below it 13 cards in four rows: Needs attention; Payments; Accounting; HR. The company switcher in the
   top bar is the one company filter: All companies, or one company (the cards and Next up then show that company only).
   Each card is read on its own route (/api/overview/<card>), drawn as soon as it comes, and one that fails says
   "Could not load, try again" on its own card without hiding the others. A card shows one headline and one note; with All
   companies a line per company, and the companies added up where they agree. Never a pay figure, an IC, a bank account
   number or anything personal (the server gives counts and totals only). */
const OV_ROWS = [
  { key: "attention", ids: ["attention"] },
  { key: "payments", head: m => `Payments · ${monthName(m)}`, ids: ["checklist", "due", "funds", "unapproved"] },
  { key: "accounting", head: m => `Accounting · ${monthName(m)}, balances as at today`, ids: ["bank", "pl", "customers", "suppliers"] },
  { key: "hr", head: () => "HR · today", note: "No pay, IC, leave type or medical detail", ids: ["leave", "dates", "headcount", "requests"] },
];
const OV = { seq: 0, data: {}, done: null, act: null, rollGone: {}, scope: null };
// The company the switcher chose, or null for All companies.
const ovScope = () => state.view === "overview" && !state.addr.all ? state.entity : null;
const ovQuery = () => `month=${state.month}${ovScope() ? `&entity_id=${ovScope()}` : ""}`;
const monthOnly = k => monthName(k).split(" ")[0];
const r0 = n => Math.round(Math.abs(Number(n) || 0)).toLocaleString("en-MY");
const curWord = c => c === "MYR" ? "RM" : c;
// Whole ringgit (or another currency), keeping the sign: an overdrawn balance reads -RM 1,250.
const money0 = (n, c = "MYR") => `${Math.round(Number(n) || 0) < 0 ? "-" : ""}${curWord(c)} ${r0(n)}`;
// Sums per currency, ringgit first: "RM 1,250.00 and USD 300.00".
const sumsText = (sums, round) => Object.entries(sums || {}).sort((a, b) => (a[0] !== "MYR") - (b[0] !== "MYR"))
  .map(([c, n]) => round ? money0(n, c) : money(n, c)).join(" and ");
// A link to a page for a company and month, as an address (core/router.js).
const ovHref = (view, entity, params = {}, month = state.month) => addrOf({ view, entity, month, sub: null, id: null, params }) || null;
const WEEKDAY_LONG = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
function longDay(iso) { const [y, m, d] = iso.split("-").map(Number); return `${WEEKDAY_LONG[new Date(y, m - 1, d).getDay()]} ${d} ${monthName(iso.slice(0, 7))}`; }

// ---------- the calm cards: per company, either { empty, short } or { u, n, head, headTone, line, lineTone, note, zero } ----------
// u is the unit: the companies are added up (sum) only when every company shown has the same one; else the main company's
// figure, its code in the note. asZero: an empty company that counts as none in a total. extra: a line of its own under the
// note (Before tracking). bit: that company's sentence for "where the figures come from".
const OV_CARDS = {
  attention: { title: "Needs attention", glyph: "alert", tone: "bad", follows: true },
  checklist: { title: "Checklist", glyph: "checklist", tone: "brand", follows: true, empty: "No checklist for this month yet",
    open: "Open checklist", where: ", Payments, Monthly checklist",
    href: c => ovHref("checklist", c.entity_id),
    src: () => `Items ticked on the Monthly checklist for ${monthName(state.month)}, out of that month's total.`,
    get: c => c.empty ? { empty: c.empty, short: "No checklist yet", note: c.tracked_from ? `Tracked from ${monthName(c.tracked_from)}` : "" }
      : { u: "items", n: c.done, t: c.total, head: `${c.done} of ${c.total}`, line: `${c.done} of ${c.total}`,
        note: c.total - c.done ? `${c.total - c.done} still to do` : `All done${c.filed_at ? `, filed ${shortDate(c.filed_at)}` : ""}` },
    sum: L => { const n = L.reduce((s, x) => s + x.n, 0), t = L.reduce((s, x) => s + x.t, 0); return { head: `${n} of ${t}`, note: t - n ? `${t - n} still to do` : "All done" }; } },
  due: { title: "Due and overdue", glyph: "clock", tone: "warn", today: true, empty: "Nothing due", open: "Open payments not paid", where: ", Payments, Payments register, Not paid",
    href: c => ovHref("entity", c.entity_id, { tab: "unpaid" }, c.link_month || state.month),
    src: () => "Payments out not paid yet, as at today: what is overdue, and what falls due in the next 7 days, from every month still open.",
    get: c => {
      const n = c.overdue.n, n2 = c.soon.n, soon = n2 ? `${n2} due in the next ${c.days} days` : `nothing due in the next ${c.days} days`;
      const payN = (c.overdue.pay_n || 0) + (c.soon.pay_n || 0);
      const bit = `${c.code}: ${n} overdue${n && sumsText(c.overdue.sums) ? `, ${sumsText(c.overdue.sums)}` : ""}; ${soon}${n2 && sumsText(c.soon.sums) ? `, ${sumsText(c.soon.sums)}` : ""}.`
        + (payN ? ` ${plural(payN, "pay payment")} (a salary, an allowance) counted but not added to the amounts.` : "");
      if (!n && !n2) return { u: "n", n: 0, n2: 0, zero: true, head: "0 overdue", headTone: "muted", line: "None", note: soon };
      return { u: "n", n, n2, head: `${n} overdue`, headTone: n ? "bad" : "", line: n ? `${sumsText(c.overdue.sums) || plural(n, "payment")} overdue` : `${n2} due`, lineTone: n ? "bad" : "",
        note: soon + (n2 && sumsText(c.soon.sums, true) ? `, ${sumsText(c.soon.sums, true)}` : ""), bit };
    },
    sum: L => { const n = L.reduce((s, x) => s + x.n, 0), n2 = L.reduce((s, x) => s + x.n2, 0); return { head: `${n} overdue`, headTone: n ? "bad" : "muted", note: n2 ? `${n2} due in the next 7 days` : "nothing due in the next 7 days" }; } },
  funds: { title: "Funds to request", glyph: "budget", tone: "brand", follows: true, empty: "Enter the bank balance to see funds to request", open: "Open Budget", where: ", Payments, Budget",
    href: c => ovHref("budget", c.entity_id),
    src: () => `From the Budget: what is still to pay for ${monthName(state.month)}, less the bank balance entered on the budget's balance date.`,
    get: c => {
      if (!c.set_up) return { empty: c.empty, short: "Not set up" };
      // No balance entered: the funds are not known, so no total is drawn while any company's are (unknown).
      if (c.funds == null) return { empty: c.empty, short: "Balance not entered", unknown: true };
      return { u: "RM", n: c.funds, head: money0(c.funds), line: money(c.funds), note: c.funds ? "to cover what's still to pay" : "the balance covers what's still to pay",
        bit: c.pay_only ? `${c.code}: what is still to pay is pay alone, so it is not shown here.`
          : `${c.code}: still to pay ${money(c.still_to_pay)}, less ${money(c.balance)} in ${c.bank || "the bank"} on ${shortDate(c.as_at)}.` };
    },
    unknownWhy: "bank balance not entered", partial: "none",
    sum: L => ({ head: money0(L.reduce((s, x) => s + x.n, 0)), note: "to cover what's still to pay" }) },
  unapproved: { title: "Paid without approval on file", glyph: "approval", tone: "bad", follows: true, hidden: true },
  bank: { title: "Bank", glyph: "bank", tone: "brand", follows: true, empty: () => `No statement imported for ${monthName(state.month)}`, open: "Open bank", where: ", Accounting, Bank and reconciliation",
    href: c => ovHref("bank", c.entity_id),
    src: () => "Balances at the latest statement line; in and out are the month's statement lines.",
    stale: cs => { const s = cs.filter(c => c.stale && c.runs_to).map(c => c.runs_to).sort()[0]; return s ? `Statement runs to ${shortDate(s)}` : ""; },
    get: c => {
      if (c.empty) return { empty: c.empty, short: "No statement" };
      const { head, note } = bankWords(c.totals);
      const curs = bankCurs(c.totals);
      return { u: "bank", totals: c.totals, head, line: curs.map(k => money(c.totals[k].balance, k)).join(" · "), note,
        bit: `${c.code}: ${c.accounts.map(a => `${a.label} ${money(a.balance, a.currency)} on ${shortDate(a.date)}`).join("; ")}.` };
    },
    // Each currency is added up on its own, across the companies that hold it; never one currency into another.
    sum: L => { const t = {};
      for (const x of L) for (const [k, v] of Object.entries(x.totals)) { const s = t[k] ||= { balance: 0, in: 0, out: 0 }; s.balance += v.balance; s.in += v.in; s.out += v.out; }
      return bankWords(t); } },
  pl: { title: "Profit or loss", glyph: "chart", tone: "brand", follows: true, sql: true, empty: "No books yet", open: "Open Books", where: ", Accounting, Books, Profit and loss",
    href: c => ovHref("books", c.entity_id, { tab: "pl" }),
    src: cs => { const to = cs.map(c => c.sql_to).filter(Boolean).sort()[0]; return to ? `From SQL's books, journal to ${shortDate(to)}.` : "From the books."; },
    stale: cs => { const s = cs.filter(c => c.stale).map(c => c.sql_to).sort()[0]; return s ? `SQL data runs to ${shortDate(s)}, fetch again` : ""; },
    get: c => {
      if (c.empty) return { empty: c.empty, short: c.empty === "No books yet" ? "No books yet" : "Nothing fetched" };
      const word = sen => sen < 0 ? "Loss" : "Profit", ytd = c.ytd_sen == null ? "year to date can't be worked out" : `${word(c.ytd_sen)} ${money0(Math.abs(c.ytd_sen / 100))} year to ${c.upto < `${state.month}-01` || c.upto < lastDay(state.month) ? shortDate(c.upto) : "date"}`;
      // The month can't be worked out: never counted as 0 in a total (unknown).
      if (c.month_sen == null) return { u: "RM", n: 0, unknown: true, head: "—", headTone: "muted", line: "Not worked out", lineTone: "muted", note: ytd,
        bit: c.upto < `${state.month}-01` ? `${c.code}: SQL's data runs to ${shortDate(c.sql_to)}, before ${monthName(state.month)}.` : `${c.code}: an opening balance is missing, so the month can't be worked out.` };
      const m = c.month_sen / 100;
      return { u: "RM", n: m, head: `${word(c.month_sen)} ${money0(Math.abs(m))}`, headTone: m < 0 ? "bad" : "", line: `${word(c.month_sen)} ${money(Math.abs(m))}`, lineTone: m < 0 ? "bad" : "", note: ytd };
    },
    unknownWhy: "the month can't be worked out", partial: "leave_out",
    sum: L => { const n = L.reduce((s, x) => s + x.n, 0); return { head: `${n < 0 ? "Loss" : "Profit"} ${money0(Math.abs(n))}`, headTone: n < 0 ? "bad" : "", note: "this month, the companies together" }; } },
  customers: { title: "Customers overdue", glyph: "users", tone: "brand", today: true, sql: true, empty: "No balances", open: "Open customers", where: ", Accounting, Customers and suppliers, customers",
    href: c => ovHref("parties", c.entity_id),
    src: cs => { const to = cs.map(c => c.sql_to).filter(Boolean).sort()[0]; return `${to ? `As at ${shortDate(to)}, from SQL. ` : ""}Balances older than 30 days. Balances brought forward from before tracking are not counted as overdue: they show apart, as Before tracking.`; },
    stale: cs => { const s = cs.filter(c => c.stale).map(c => c.sql_to).sort()[0]; return s ? `as at ${shortDate(s)}, fetch again` : ""; },
    get: c => {
      if (c.empty && !c.before_tracking_sen) return { empty: c.empty, short: c.empty === "No balances" ? "None" : "Nothing fetched", asZero: c.empty === "No balances" };
      const n = c.overdue_sen / 100, bt = c.before_tracking_sen / 100, k = c.overdue_count;
      const extra = bt ? `Before tracking ${money0(bt)}` : "";
      return { u: "RM", n, k, bt, zero: !n && !bt, head: money0(n), headTone: n ? "bad" : "muted", line: n ? money(n) : "None", lineTone: n ? "bad" : "muted",
        note: k ? `${plural(k, "balance")} over 30 days` : "no balances over 30 days", extra,
        bit: bt ? `${c.code}: ${money(bt)} brought forward from before tracking (${plural(c.before_tracking_count, "balance")}), not counted as overdue.` : "" };
    },
    sum: L => { const n = L.reduce((s, x) => s + x.n, 0), k = L.reduce((s, x) => s + (x.k || 0), 0), bt = L.reduce((s, x) => s + (x.bt || 0), 0);
      return { head: money0(n), headTone: n ? "bad" : "muted", note: `${plural(k, "balance")} over 30 days`, extra: bt ? `Before tracking ${money0(bt)}` : "" }; } },
  suppliers: { title: "Suppliers due", glyph: "inbox", tone: "brand", today: true, sql: true, empty: "No balances", open: "Open suppliers", where: ", Accounting, Customers and suppliers, suppliers",
    href: c => ovHref("parties", c.entity_id, { tab: "suppliers" }),
    src: cs => { const to = cs.map(c => c.sql_to).filter(Boolean).sort()[0]; return `${to ? `As at ${shortDate(to)}, from SQL. ` : ""}Bills overdue, and bills due in the next 14 days (a bill is taken as due 30 days after its date: SQL's exports carry no due dates).`; },
    stale: cs => { const s = cs.filter(c => c.stale).map(c => c.sql_to).sort()[0]; return s ? `as at ${shortDate(s)}, fetch again` : ""; },
    get: c => {
      if (c.empty && !c.before_tracking_sen) return { empty: c.empty, short: c.empty === "No balances" ? "None" : "Nothing fetched", asZero: c.empty === "No balances" };
      const n = c.overdue_sen / 100, d = c.due_sen / 100, bt = c.before_tracking_sen / 100;
      return { u: "RM", n, d14: d, bt, zero: !n && !d && !bt, head: `${money0(n)} overdue`, headTone: n ? "bad" : "muted", line: n ? `${money(n)} overdue` : "None", lineTone: n ? "bad" : "muted",
        note: d ? `${money0(d)} due in the next ${c.days} days` : `none due in the next ${c.days} days`, extra: bt ? `Before tracking ${money0(bt)}` : "",
        bit: c.overdue_count ? `${c.code}: ${plural(c.overdue_count, "bill")} overdue.` : "" };
    },
    sum: L => { const n = L.reduce((s, x) => s + x.n, 0), d = L.reduce((s, x) => s + (x.d14 || 0), 0), bt = L.reduce((s, x) => s + (x.bt || 0), 0);
      return { head: `${money0(n)} overdue`, headTone: n ? "bad" : "muted", note: d ? `${money0(d)} due in the next 14 days` : "none due in the next 14 days", extra: bt ? `Before tracking ${money0(bt)}` : "" }; } },
  // HR: the staff records come with slices 12 and 13, requests with slice 11. No link while empty.
  leave: { title: "On leave", glyph: "leave", tone: "brand", today: true, empty: "Add your staff to see this", src: () => "From Leave, for today and this week. The type of leave is never shown.", get: c => ({ empty: c.empty, short: "No staff yet" }) },
  dates: { title: "Dates coming up", glyph: "reminder", tone: "brand", today: true, empty: "Add your staff to see this", src: () => "Probation, contract, passport and permit dates in the next 60 days, counted with no names, and this month's birthdays and work anniversaries.", get: c => ({ empty: c.empty, short: "No staff yet" }) },
  headcount: { title: "Headcount", glyph: "staff", tone: "brand", today: true, empty: "Add your staff to see this", src: () => "From Staff, as at today: people in employment, and joiners and leavers this month.", get: c => ({ empty: c.empty, short: "No staff yet" }) },
  requests: { title: "Requests waiting", glyph: "claim", tone: "brand", today: true, empty: "Nothing waiting", src: () => "Waiting for approval on Approvals, and approved but not yet paid.", get: c => ({ empty: c.empty, short: "None" }) },
};
// The Bank card's words for balances per currency: the ringgit (else the first) currency as the headline with its in and out,
// every other currency's balance named after it ("also USD 17,480"). Balances keep their sign.
const bankCurs = totals => Object.keys(totals).sort((a, b) => (a !== "MYR") - (b !== "MYR") || (a < b ? -1 : 1));
function bankWords(totals) {
  const curs = bankCurs(totals), u = curs[0], t = totals[u];
  const more = curs.slice(1).map(k => money0(totals[k].balance, k)).join(", ");
  return { head: money0(t.balance, u), note: `in ${money0(t.in, u)} · out ${money0(t.out, u)}` + (more ? ` · also ${more}` : "") };
}
const lastDay = m => { const [y, mm] = m.split("-").map(Number); return `${m}-${String(new Date(y, mm, 0).getDate()).padStart(2, "0")}`; };

// ---------- Needs attention: five counters per company, each opening its list ----------
const OV_COUNTERS = [
  ["past_due", "Past due", "bad", c => ovHref("entity", c.entity_id, { tab: "unpaid", mark: "past_due" })],
  ["part_paid", "Part paid", "warn", c => ovHref("entity", c.entity_id, { tab: "attention", mark: "part_paid" })],
  ["docs_missing", "Documents missing", "warn", c => ovHref("checklist", c.entity_id, { tab: "missing" })],
  ["to_explain", "Lines to explain", "warn", c => ovHref("bank", c.entity_id, { filter: "to_explain" })],
  ["not_in_sql", "Not in SQL", "warn", c => ovHref("entity", c.entity_id, { tab: "nosql" })],
];
function ovAttention(d) {
  const all = !ovScope(), cs = d.companies;
  const zero = c => OV_COUNTERS.every(([k]) => !c[k]);
  if (cs.every(zero)) return ovBody("attention", `<div class="ovb"><span class="ove">Nothing needs attention</span>${cs.length === 1 && cs[0].filed ? `<span class="sub">${esc(monthName(state.month))} is filed</span>` : ""}</div>`, { empty: true });
  const blocks = cs.map(c => {
    const ctrs = OV_COUNTERS.filter(([k]) => c[k] != null).map(([k, label, tone, href]) => {
      const n = c[k];
      return `<a class="ctr" href="${esc(href(c) || "#/")}" id="ov-ctr-${k}-${c.entity_id}" aria-label="${esc(`${label}, ${n || "none"}${all ? `, ${c.code}` : ""}. Opens its list`)}"><b class="ctr-n${n ? " " + tone : ""}">${n}</b><span>${label}</span></a>`;
    }).join("");
    const note = c.filed ? "Filed: nothing in it counts as to do" : c.before_tracking ? "Before tracking: only the lines to explain count" : "";
    return `<div class="ova">${all ? ovCo(c) : ""}<div class="ova-ctrs">${ctrs}</div>${note ? `<span class="sub">${note}</span>` : ""}</div>`;
  }).join("");
  return ovBody("attention", blocks, { foot: "Each number opens its list, filtered" });
}
const ovCo = c => `<span class="ovco-head"><span class="cp ${c.kind === "sql" ? "info" : "mute"}">${esc(c.code)}</span><span class="sub">${esc(c.kind_label)}</span></span>`;

// ---------- a card's frame ----------
function ovFrame(id, inner, { tone, link } = {}) {
  const C = OV_CARDS[id], t = tone || C.tone;
  return `<article class="ovc${link ? " lk" : ""}${id === "attention" ? " ova-card" : ""}" aria-labelledby="ov-h-${id}">
    <div class="ovt"><span class="ov-tile ${t}" aria-hidden="true">${icon(C.glyph)}</span><h3 id="ov-h-${id}" class="ovtt" tabindex="-1">${esc(C.title)}</h3>${C.today ? `<span class="tday">Today</span>` : C.follows ? `<span class="sub">${esc(monthName(state.month))}</span>` : ""}</div>
    ${inner}</article>`;
}
function ovBody(id, inner, { empty, foot } = {}) {
  return ovFrame(id, `${inner}${foot ? `<div class="ovf"><span class="sub">${esc(foot)}</span></div>` : ""}`, { tone: empty ? "muted" : undefined });
}
const ovLoading = id => ovFrame(id, `<div aria-busy="true" class="ov-sk"><span class="sr-only">Loading ${esc(OV_CARDS[id].title)}</span><div class="sk" style="width:60%"></div><div class="sk"></div></div>`, { tone: "muted" });
const ovFailed = (id, why) => ovFrame(id, `<div class="ov-fail"><span role="alert">${icon("alert")}Could not load, try again</span>
  <button type="button" class="ghost small" id="ov-retry-${id}" data-ov-retry="${id}" title="${esc(why || "")}">${icon("refresh")}Try again</button></div>
  <div class="ovf"><span class="sub">The other cards are not affected</span></div>`, { tone: "bad" });

// A calm card from the server's answer d, as Main.dc.html's card2 draws it.
function ovCalm(id, d) {
  const C = OV_CARDS[id], cs = d.companies, per = cs.map(c => ({ c, v: C.get(c) }));
  const none = per.every(x => x.v.empty || x.v.zero), many = per.length > 1;
  const live = per.filter(x => !x.v.empty);
  const agree = live.length > 0 && per.every(x => !x.v.empty || x.v.asZero) && new Set(live.map(x => x.v.u)).size === 1;
  const main = live.find(x => !x.v.zero) || live[0] || per[0];
  const dEmpty = typeof C.empty === "function" ? C.empty() : C.empty;
  let head = "", note = "", headTone = "", extra = "";
  // A company whose figure is not known (no bank balance entered, a month that can't be worked out) is never added as 0:
  // with it there is no total (partial "none"), or a total of the others that says it leaves that company out ("leave_out").
  const unknown = per.filter(x => x.v.unknown), known = live.filter(x => !x.v.unknown);
  if (!none && many && unknown.length && C.sum) {
    const codes = unknown.map(x => x.c.code).join(" and ");
    if (C.partial === "leave_out" && known.length && new Set(known.map(x => x.v.u)).size === 1) {
      const s = C.sum(known.map(x => x.v)); head = s.head; headTone = s.headTone || ""; note = `${s.note || ""} · leaves out ${codes}: ${C.unknownWhy}`;
    } else { head = "No total"; headTone = "muted"; note = `${codes}: ${C.unknownWhy}`; }
  } else if (!none) {
    if (many && agree && C.sum) { const s = C.sum(live.map(x => x.v)); head = s.head; note = s.note || ""; headTone = s.headTone || ""; extra = s.extra || ""; }
    else { head = main.v.head; headTone = main.v.headTone || ""; note = main.v.note || ""; extra = main.v.extra || ""; if (many) note = main.c.code + (note ? " · " + note : " only"); }
  }
  const sentences = [...new Set(per.map(x => x.v.empty || dEmpty))];
  const emptyText = sentences.length === 1 ? sentences[0] : (per[0]?.v.empty || dEmpty);
  if (none && !many) note = per[0]?.v.empty && per[0].v.note || "";
  const lines = many && (!none || sentences.length > 1) ? per.map(({ c, v }) =>
    `<span class="ovr"><span class="ovco">${esc(c.code)}</span><b class="${v.empty || v.zero || v.lineTone === "muted" ? "muted" : v.lineTone === "bad" ? "bad" : ""}">${esc(v.empty ? v.short : v.line)}</b></span>`).join("") : "";
  const stale = C.stale ? C.stale(cs) : "";
  const target = C.href && (cs.find(c => { const v = C.get(c); return !v.empty && !v.zero; }) || cs[0]);
  const href = target ? C.href(target) : null;
  const source = [C.src ? C.src(cs) : "", ...per.map(x => x.v.bit).filter(Boolean)].join(" ");
  const body = none
    ? `<div class="ovb"><span class="ove">${esc(emptyText)}</span>${note ? `<span class="sub ovn">${esc(note)}</span>` : ""}</div>`
    : `<div class="ovb"><b class="ovh ${headTone}">${esc(head)}</b>${note ? `<span class="sub ovn">${esc(note)}</span>` : ""}${extra ? `<span class="ov-bt">${esc(extra)}</span>` : ""}</div>`;
  return ovFrame(id, `${body}${stale ? `<span class="ovw">${icon("clock")}${esc(stale)}</span>` : ""}${lines ? `<div class="ovk">${lines}</div>` : ""}
    <div class="ovf">${href ? `<a class="ovo" id="ov-link-${id}" href="${esc(href)}">${esc(C.open)}<span class="sr-only">${esc(C.where || "")}</span><span aria-hidden="true">›</span></a>` : `<span></span>`}
      ${source ? `<details class="ovtip"><summary aria-label="${esc(`Where the figures come from: ${C.title}`)}">${icon("help")}</summary><p>${esc(source)}</p></details>` : ""}</div>`,
    { tone: none ? "muted" : undefined, link: !!href });
}

// Draws one card into its place, from what was read (d), its failure (err), or while it loads.
function ovPaint(id) {
  const slot = $(`#ov-c-${id}`);
  let x = OV.data[id];
  if (!slot) return;
  const C = OV_CARDS[id];
  if (x && x.d && !Array.isArray(x.d.companies)) x = OV.data[id] = { err: "The answer had no companies in it" };
  else if (x && x.d && (C.hidden || x.d.companies.every(c => c.hidden))) { slot.innerHTML = ""; slot.hidden = true; return; }
  slot.hidden = false;
  let html;
  try { html = !x || x.busy ? ovLoading(id) : x.err ? ovFailed(id, x.err) : id === "attention" ? ovAttention(x.d) : ovCalm(id, x.d); }
  catch (e) { html = ovFailed(id, e.message); }  // an answer the card can't read fails that card alone
  slot.innerHTML = html;
}
// Reads one card (its own route) and draws it; seq: the Overview drawn, so a late answer for a page since left is dropped.
async function ovLoad(id, seq) {
  OV.data[id] = { busy: true }; ovPaint(id);
  let x;
  try { x = { d: await api(`/api/overview/${id}?${ovQuery()}`) }; } catch (e) { x = { err: e.message || "Could not load" }; }
  if (seq !== OV.seq || state.view !== "overview") return false;
  OV.data[id] = x; ovPaint(id);
  return true;
}
// The page the answer was asked for is still on show: the same Overview drawn, the same month and company choice.
const ovSame = (seq, month, scope) => seq === OV.seq && state.view === "overview" && state.month === month && ovScope() === scope;
// Try again on one card: only that card is read again; once it is back and drawn, on the same page, the focus goes to its
// link (else its first counter, else its heading). An answer dropped as late moves no focus.
async function ovRetry(id) {
  if (!OV_CARDS[id]) return;
  const seq = OV.seq, month = state.month, scope = ovScope();
  if (!(await ovLoad(id, seq)) || !ovSame(seq, month, scope)) return;
  const first = OV.data[id]?.d?.companies?.[0];
  ($(`#ov-link-${id}`) || (first && $(`#ov-ctr-past_due-${first.entity_id}`)) || $(`#ov-h-${id}`))?.focus?.({ preventScroll: true });
}

// ---------- Recent activity ----------
const ovWhen = at => { const d = at.slice(0, 10); return d === dayKey() ? `today ${at.slice(11, 16)}` : shortDate(d); };
function ovActHtml(r) {
  if (!r) return `<div aria-busy="true" class="ov-sk act"><span class="sr-only">Loading recent activity</span><div class="sk"></div><div class="sk"></div><div class="sk"></div></div>`;
  if (r.error) return `<div role="alert" class="banner bad ov-act-err">${icon("alert")}<span><b>Couldn't load recent activity</b> The audit trail didn't answer: ${esc(r.error)}. The rest of the page still works.</span><button type="button" class="ghost small" data-ov-act-retry="1">Try again</button></div>`;
  if (!r.items.length) return `<div class="ov-act-empty">${icon("trail")}<span>No activity for ${ovScope() ? esc(ent()?.code || "this company") : "these companies"} yet</span></div>`;
  return `<ul class="ov-acts">${r.items.map(a => `<li><span>${esc(a.text)}</span><span class="sub">${esc([a.who, a.company, ovWhen(a.at)].filter(Boolean).join(" · "))}</span></li>`).join("")}</ul>`;
}
async function ovActivity(seq, focus) {
  OV.act = null; const box = $("#ovAct"); if (box) box.innerHTML = ovActHtml(null);
  const month = state.month, scope = ovScope();
  let r;
  try { r = await api(`/api/overview/activity?${ovQuery()}`); } catch (e) { r = { error: e.message }; }
  if (!r.error && !Array.isArray(r.items)) r = { error: "The answer had no entries in it" };
  if (!ovSame(seq, month, scope)) return;  // a late answer for a page since left: dropped, and no focus moved
  OV.act = r; const b = $("#ovAct"); if (b) b.innerHTML = ovActHtml(r);
  if (focus) $("#ov-act-h")?.focus?.({ preventScroll: true });
}

// ---------- the rollover banner ----------
// Shown on the current payroll month when a company in view has the next month set up already: it names those companies and
// counts only their Next up rows of the month on show (build plan 4.3). Dismiss hides it for this month and company choice.
function ovRollover(ro, next) {
  const key = `${state.month}:${ovScope() || "all"}`;
  if (!ro || ro.error || !Array.isArray(ro.set_up) || next.error || OV.rollGone[key] || state.month !== currentCycle()) return "";
  const inView = (state.meta.entities || []).filter(e => isActive(e) && (!ovScope() || e.id === ovScope()));
  const named = inView.filter(e => ro.set_up.includes(e.id));
  if (!named.length) return "";
  const ids = new Set(named.map(e => e.id)), n = next.items.filter(r => r.month === state.month && ids.has(r.entity_id)).length;
  if (!n) return "";
  const nm = monthOnly(ro.next_month), title = named.length === inView.length ? `${nm} has started` : `${named.map(e => e.code).join(" and ")}'s ${nm} is set up`;
  return `<div role="status" class="banner info ov-roll noprint" id="ovRoll">${icon("calendar")}<div class="ov-roll-text"><b>${esc(title)}</b>
    <span>You are looking at ${esc(monthOnly(state.month))}, which is still open: ${plural(n, "thing")} left.</span></div>
    <div class="row"><button type="button" class="btn" data-ov-roll="go">Go to ${esc(nm)}</button><button type="button" class="ghost" data-ov-roll="dismiss">Dismiss</button></div></div>`;
}
async function ovRoll(what) {
  if (what === "dismiss") { OV.rollGone[`${state.month}:${ovScope() || "all"}`] = true; $("#ovRoll")?.remove?.(); const b = $("#ovRollBox"); if (b) b.innerHTML = ""; $("#ov-next-h")?.focus?.({ preventScroll: true }); return; }
  if (!(await closeDrawer())) return;
  state.month = shiftMonth(state.month, 1); state.addr.params = {};
  return redraw();
}

// Next up's heading says whose rows it lists: the switcher's company, or All companies (core/next.js nextCard).
function ovWho() {
  const e = ovScope() ? ent() : null;
  return `<span class="ov-who">${e ? `<span class="cp ${e.uses_sql ? "info" : "mute"}">${esc(e.code)}</span><span>${esc(keptLabel(e))} · the company button above changes it</span>`
    : `<span class="cp mute">All companies</span><span>Pick one company with the company button above</span>`}</span>`;
}

// ---------- the page ----------
async function viewOverview(main) {
  const seq = ++OV.seq, scope = ovScope();
  OV.data = {}; OV.act = null; OV.scope = scope;
  const live = (state.meta.entities || []).filter(isActive);
  if (!live.length) {
    main.innerHTML = `<section class="card ov-first"><h2>Add your first company</h2><div class="note">There is no company yet, so there is nothing to work out. Records stay on this PC. Nothing is sent anywhere.</div>
      <div class="row"><a class="btn" href="#/admin/setup/entities">${icon("plus")}Add your first company</a></div></section>`;
    OV.done = Promise.resolve();
    return;
  }
  const [next, ro] = await Promise.all([loadNext(scope), api(`/api/overview/rollover?${ovQuery()}`).catch(e => ({ error: e.message }))]);
  if (seq !== OV.seq) return;
  // Nothing answered at all (the records can't be reached): the page's own Couldn't load card, not a page of failed cards.
  if (next.error && ro.error) throw new Error(next.error);
  const budgetTo = ovHref("budget", scope || state.entity || firstEntityId());
  const rows = OV_ROWS.map(r => `<section class="ov-row" aria-labelledby="ov-row-${r.key}">
      ${r.head ? `<div class="ov-row-head"><h2 id="ov-row-${r.key}" class="rh">${esc(r.head(state.month))}</h2>${r.note ? `<span class="sub">${esc(r.note)}</span>` : ""}</div>` : `<h2 id="ov-row-${r.key}" class="sr-only">Needs attention</h2>`}
      <div class="${r.key === "attention" ? "ov-grid1" : "ovg"}">${r.ids.map(id => `<div class="ov-slot" id="ov-c-${id}"${OV_CARDS[id].hidden ? " hidden></div>" : `>${ovLoading(id)}</div>`}`).join("")}</div></section>`).join("");
  main.innerHTML = `
    <div id="ovRollBox">${ovRollover(ro, next)}</div>
    <div class="ov-head"><div class="ov-head-words"><span class="eyebrow">${esc(longDay(dayKey()))} · Payroll month</span><h1>${esc(monthName(state.month))} cycle</h1>
      <p class="ov-lead">The month's checklist and payments, including bills and statutory payments paid early in ${esc(monthOnly(shiftMonth(state.month, 1)))}.</p></div>
      <div class="row noprint">${budgetTo ? `<a class="ghost" href="${esc(budgetTo)}">${icon("budget")}Open budget</a>` : ""}<button type="button" class="btn" id="addPayment">${icon("plus")}Add a payment</button></div></div>
    <div class="ov-top">
      <div class="ov-next" id="nextUp">${nextCard(next, null)}</div>
      <section class="card ov-act" aria-labelledby="ov-act-h"><div class="row spread"><div><h2 id="ov-act-h" tabindex="-1">Recent activity</h2><span class="sub">From the audit trail, newest first · no pay or personal details</span></div>
        <a class="link" href="#/admin/audit-trail">Audit trail</a></div><div id="ovAct">${ovActHtml(null)}</div></section>
    </div>
    <div class="ov-rows">${rows}</div>
    <details class="card ov-how"><summary><h2>How a payment is completed</h2></summary>
      <div class="row"><span class="pill grey">Not paid</span> → <span class="pill warn">Paid, documents missing</span> → <span class="pill ok">Complete</span></div>
      <div class="note">A payment becomes <b>Paid</b> when you enter the paid date or its bank statement line is matched. It becomes <b>Complete</b> when every required document is uploaded, or already shown by a linked SQL voucher, a validated e-Invoice or its bank statement line. Only complete payments are ready to file.</div>
      <div class="note">Past its due date and not paid yet, a payment says why: <b>Not on Oct statement</b> (or the month it fell due in) once that month's bank statement is imported without it; until then <b>Waiting for SQL record</b> while SQL isn't imported up to its due date, or else <b>Waiting for Oct statement</b>. A statutory payment not paid by the 15th of the next month shows <b>Past legal deadline</b>.</div>
      <div class="note">If the bank lines matched add up to less than the amount, it shows <b>Part paid</b> until the rest is matched, or you note why in the payment (e.g. balance paid in October).</div>
      <div class="note">Money received (a tenant's rent, say) is set up on the Recurring page as <b>Money in</b>. It is counted apart from the payments, and is never in the Budget.</div>
    </details>`;
  const ids = OV_ROWS.flatMap(r => r.ids).filter(id => !OV_CARDS[id].hidden);
  OV.done = Promise.all([...ids.map(id => ovLoad(id, seq)), ovActivity(seq)]);
}
