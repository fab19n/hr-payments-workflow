"use strict";
/* ---------------- Payments › Budget (slice 8) ----------------
   View key budget, address #/<CODE>/<YYYY-MM>/payments/budget (?as_at= from a Next up row). Built to design/canvas/Budget.dc.html:
   the head with Excel and Print budget, the bank balance and its date, the figures (balance, still to pay, funds to request,
   already paid, other currencies), Budget vs paid, the stored budget's lines (edited in place, saved when you leave a box),
   Paid but not in the budget, Budget against paid, Already paid (in the balance), and the print preview (the budget, or the
   fund request while there is a shortfall).
   The bank balance and its date are read only from the stored budget (hrp/budget.py): nothing is kept in this browser. With no
   ringgit balance entered, Funds to request reads "Enter the bank balance to see funds to request", there is no fund request
   to print, and the print says "not worked out, bank balance not entered". The bank is named from the company's own account in
   Setup (d.bank), never written into the app. Payments paid on or before the balance date are already out of the balance. */

// A real day from the year 2000 on, as the server takes it; the date box can hold others while it is being typed in.
const isDay = v => /^[2-9]\d{3}-\d{2}-\d{2}$/.test(v) && !isNaN(new Date(v)) && new Date(v).toISOString().slice(0, 10) === v;
// The balance is taken around the budget month: a date from the month before to the month after.
function budgetRange(month) {
  const after = shiftMonth(month, 1), [ay, am] = after.split("-").map(Number);
  const first = `${shiftMonth(month, -1)}-01`, last = `${after}-${new Date(Date.UTC(ay, am, 0)).getUTCDate()}`;
  return { first, last, inRange: v => isDay(v) && v >= first && v <= last };
}
// An amount typed in a box: commas allowed, at most two decimals. null for blank, NaN for anything else.
const budgetAmount = v => { const t = String(v ?? "").trim().replace(/,/g, ""); return t === "" ? null : /^-?\d+(\.\d{1,2})?$/.test(t) ? +t : NaN; };
const plainNum = (n, cur) => money(n, cur).replace(/^\S+ /, "");
const curTitle = cur => cur === "MYR" ? "Ringgit (RM)" : esc(cur);
const curHead = cur => cur === "MYR" ? "RM" : esc(cur);
// The company's own account the ringgit balance is for (Setup › Bank accounts): its label names the bank.
function budgetBank(d) {
  const a = d.bank?.account, others = d.bank?.others || [], code = esc(d.entity.code), st = d.bank?.stopped;
  if (a) return { label: a.label, line: `${code} · ${esc(a.label)}`, sub: `${esc(a.label)} · from the bank's app or statement` };
  if (st) return { label: null, line: code, sub: `${esc(st.label)} is stopped; use it again or add another ringgit account under Setup › Bank accounts` };
  if (others.length) {
    const names = others.map(o => `${esc(o.label)} (${esc(o.currency)})`).join(", ");
    return { label: null, line: code, sub: `${code}'s only account${others.length > 1 ? "s are" : " is"} ${names}, so no RM balance is entered` };
  }
  return { label: null, line: code, sub: `No bank account is set up for ${code} yet: add one under Setup › Bank accounts` };
}

// The stored balance is for another date than the one the page is at (a Next up row opens it as at today): it is left
// out, so it is never set against what is still to pay at this date; the server gives no funds to request then either.
const budgetOther = d => !!(d.stored && d.balance != null && d.saved_as_at && d.saved_as_at !== d.as_at);

// What the page keeps while it is open on one company and month: how many lines show per currency, the lines picked.
// picked: {key, at}, a date chosen while the page was being read, for a budget not set up (its date is kept nowhere).
const BUD = { key: null, printing: null, shown: {}, sel: new Set(), paidOpen: true, tick: null, visible: new Set(), picked: null };
const BUD_STEP = 25;

async function viewBudget(main) { return pageDraw("main", page => budgetDraw(page, main)); }
async function budgetDraw(page, main) {
  // From a row of Next up (as_at: today) the page is as at that day, which is what the row totals; the balance kept with the
  // budget is for its own date, so it is left out until that date is asked for ("Use <date>"). The day is used up only when the
  // page is written, so a draw overtaken or failed at any of its reads doesn't lose it.
  let here = state.asAt;
  const asked = here, key = `${state.entity}:${state.month}`;
  if (BUD.key !== key) Object.assign(BUD, { key, shown: {}, sel: new Set(), paidOpen: true, visible: new Set() });
  BUD.printing = null; BUD.tick = null; BUD.picked = null;
  const load = asAt => api(`/api/budget?entity=${state.entity}&month=${state.month}${asAt ? "&as_at=" + asAt : ""}`);
  let d = await page.read(load(here));
  // A balance this browser kept before slice 8 goes across to the stored budget once (core/legacy.js). It is a change made while
  // the page is read: if the page can't be read after it, render() says it was saved (kept).
  if (await page.read(carryBrowserBalance(d))) d = await page.read(load(here).catch(e => { throw Object.assign(e, { kept: true }); }));
  // A date chosen in the page still on show while this one was read: it is read for that date.
  for (let done = null; BUD.picked?.key === key && BUD.picked !== done;) { done = BUD.picked; here = null; d = await page.read(load(done.at)); }
  if (state.asAt === asked) state.asAt = null;
  const held = d.stored ? d.lines.length : d.to_pay.length + d.paid.length;
  if (!d.stored && !d.set_up && !held && !d.previous) {
    main.innerHTML = `<div id="bud">${budgetHead(d, false)}${emptyState({ glyph: "calendar", title: `${monthName(d.month)} isn't set up yet`,
      body: "Setting it up adds the month's recurring payments and checklist. The budget is made from the month's payments.",
      action: { label: "Set up this month", attr: "data-open-month", value: String(d.entity.id) } })}</div>`;
    return;
  }
  const R = budgetRange(d.month);
  // The page is drawn inside one box that stays, so its listeners (below) are added once.
  main.innerHTML = `<div id="bud" class="bud"></div>`;
  const box = $("#bud");
  const draw = () => {
    if (BUD.printing) { box.innerHTML = budgetPrint(d, BUD.printing); $("#bud-print-h")?.focus?.({ preventScroll: true }); return; }
    // A line box being typed in when the page is drawn again (after another box saved) keeps its focus and its text.
    const act = document.activeElement, at = act?.dataset?.f && act.closest?.("tr[data-line]");
    const keep = at ? { line: at.dataset.line, f: act.dataset.f, v: act.value } : null;
    box.innerHTML = budgetPage(d, here, R);
    if (keep) {
      const el = document.querySelector?.(`tr[data-line="${keep.line}"] [data-f="${keep.f}"]`);
      if (el) { el.focus(); if (el.tagName === "INPUT") el.value = keep.v; }
    }
  };
  // Reading the budget again to draw it in this box is a part of the page (core/page.js): of two reads, the one asked for last is
  // drawn. Resolves true when it drew.
  const refresh = asAt => pageDraw("budget", async part => { d = await part.read(load(asAt || d.as_at)); draw(); return true; });
  const shown = () => state.view === "budget" && BUD.key === key && box.isConnected !== false;
  // A change: sent, then the page drawn again from the server. ok(r) runs once the server took it, before the reading back (its
  // message, a tick); then(r) once the page has been drawn with it.
  const change = async (call, then, ok) => {
    let r;
    try { r = await call(); }
    catch (e) { toast(changeError(e), true); try { await refresh(); } catch {} return false; }
    if (ok) ok(r);
    let drew = false;
    await afterSaved(savedPart(shown, async () => { drew = await refresh(); }));  // the lines are a part of their own, never the page's own draw
    if (drew && then) then(r);
    return true;
  };
  const eid = d.entity.id, month = d.month;
  const header = body => api("/api/budget/header", { json: { entity_id: eid, month, ...body } });
  const remove = async (ids, title, text, list) => (await ask(text, { title, yes: ids.length === 1 ? "Delete line" : `Delete ${ids.length} lines`, no: "Cancel", danger: true, tone: "bad", glyph: "trash",
    list, note: "The payments themselves are not changed. Each deleted line keeps its History." })) && change(() => api("/api/budget/lines/delete", { json: { ids } }));
  let opener = null, saving = false;

  // The balance: saved on the stored budget when you leave the box or press Enter (once: Enter then the box's change while
  // the save is under way send it one time). Blank is "not entered", never 0. "Saved" shows only once the server took it.
  const saveBalance = async () => {
    const box = $("#bud-bal"); if (!box || !d.stored || saving) return;
    const n = budgetAmount(box.value);
    if (Number.isNaN(n)) { markField("bud-bal", "Enter an amount such as 10,000.00"); return; }
    markField("bud-bal", "");
    const other = budgetOther(d), was = other ? null : d.balance;
    if (n === was) return;
    // The date goes with the balance: the one kept with it; else a date typed in the date box (the page's date when it is
    // at another date than the one kept); never today filled in unasked, so the "Enter the date" note stays until one is.
    const dateBox = $("#bud-date")?.value;
    const at = !other && d.saved_as_at ? d.saved_as_at : R.inRange(dateBox) ? dateBox : null;
    BUD.tick = null; saving = true;
    try { await change(() => header({ balance: n, ...(at ? { as_at: at } : {}) }), null, () => { if (shown()) BUD.tick = "bal"; }); }
    finally { saving = false; }
  };
  const saveDate = async () => {
    const v = $("#bud-date")?.value || "";
    if (!R.inRange(v)) {
      if (v) markField("bud-date", `Choose a date between ${shortDate(R.first)} and ${shortDate(R.last)}`);
      return;
    }
    markField("bud-date", "");
    if (!d.stored) {  // nothing to keep: the list follows the date; while the page is being read again, its own draw reads for it
      if (!pageWhole()) { BUD.picked = { key: `${d.entity.id}:${d.month}`, at: v }; return; }
      try { await refresh(v); } catch (e) { toast(e.message, true); }
      return;
    }
    BUD.tick = null;
    await change(async () => { await header({ as_at: v }); d.as_at = v; }, null, () => { if (shown()) BUD.tick = "date"; });
  };

  draw();
  box.addEventListener("change", e => {
    const t = e.target, tr = t.closest?.("tr[data-line]");
    if (t.id === "bud-bal") return saveBalance();
    if (t.id === "bud-date") return saveDate();
    if (t.id === "bud-all") { BUD.sel.clear(); if (t.checked) BUD.visible.forEach(id => BUD.sel.add(id)); return draw(); }  // the lines shown only
    if (t.dataset?.sel) { t.checked ? BUD.sel.add(+t.dataset.sel) : BUD.sel.delete(+t.dataset.sel); return draw(); }
    if (!tr || !t.dataset?.f) return;
    let v = t.value;
    if (t.dataset.f === "payment_id") v = v ? +v : null;
    if (t.dataset.f === "amount") {
      const n = budgetAmount(v);
      if (Number.isNaN(n) || n < 0) return markField(t.id, "Enter an amount such as 10,000.00");
      markField(t.id, ""); v = n;
    }
    change(() => api(`/api/budget/lines/${tr.dataset.line}`, { method: "PATCH", json: { [t.dataset.f]: v } }));
  });
  box.addEventListener("input", e => { if (e.target.id === "bud-bal" || e.target.id === "bud-date") { BUD.tick = null; $("#bud-tick-bal")?.remove?.(); $("#bud-tick-date")?.remove?.(); } });
  box.addEventListener("keydown", e => {
    if (e.key !== "Enter") return;
    if (e.target.id === "bud-bal") { e.preventDefault(); return saveBalance(); }
    if (e.target.classList?.contains("cell")) e.target.blur();
  });
  box.addEventListener("click", e => {
    const t = e.target.closest?.("button");
    if (!t) return;
    const ds = t.dataset;
    if (ds.budPrint) { opener = t.id; BUD.printing = ds.budPrint; return draw(); }
    if (t.id === "bud-print-back") { BUD.printing = null; draw(); return $(`#${opener || "bud-print"}`)?.focus?.({ preventScroll: true }); }
    if (t.id === "bud-print-go") return window.print();
    if (t.id === "bud-setup") return setUpBudget(d);
    if (ds.budMore) { BUD.shown[ds.budMore] = (BUD.shown[ds.budMore] ?? BUD_STEP) + BUD_STEP; return draw(); }
    if (ds.budPaid) { BUD.paidOpen = !BUD.paidOpen; draw(); return $("#bud-paid-btn")?.focus?.({ preventScroll: true }); }
    if (ds.add) return change(() => api("/api/budget/lines", { json: { entity_id: eid, month, currency: ds.add } }),
      r => { BUD.shown[ds.add] = Math.max(BUD.shown[ds.add] ?? BUD_STEP, d.lines.filter(x => x.currency === ds.add).length); draw();
        document.querySelector?.(`tr[data-line="${r.result}"] [data-f="description"]`)?.focus(); toast("Line added. Describe it and set its amount."); });
    if (ds.addPayment) return change(() => api("/api/budget/lines", { json: { entity_id: eid, month, payment_id: +ds.addPayment } }), null, () => toast("Added to the budget"));
    if (ds.del) {
      const x = d.lines.find(l => l.id === +ds.del);
      return remove([+ds.del], "Delete this line?", "The line comes out of the budget. This cannot be undone here.",
        x ? [{ glyph: "trash", tone: "muted", text: `${x.description || "New line"} · ${money(x.amount || 0, x.currency)}` }] : []);
    }
    if (t.id === "bud-delsel") {
      const gone = d.lines.filter(x => BUD.sel.has(x.id) && BUD.visible.has(x.id)), ids = gone.map(x => x.id);  // only lines shown
      if (!ids.length) return;
      return remove(ids, ids.length === 1 ? "Delete this line?" : `Delete ${ids.length} lines?`,
        ids.length === 1 ? "The line comes out of the budget. This cannot be undone here." : `These ${ids.length} lines come out of the budget. This cannot be undone here.`,
        gone.map(x => ({ glyph: "trash", tone: "muted", text: `${x.description || "New line"} · ${money(x.amount || 0, x.currency)}` })));
    }
  });
}

async function setUpBudget(d) {
  try {
    const r = await api("/api/budget/setup", { json: { entity_id: d.entity.id, month: d.month } });
    toast(`Budget set up with ${r.result} line${r.result === 1 ? "" : "s"}`);
  } catch (e) { return toast(changeError(e), true); }
  await afterSaved(render);
}

const cycleNote = d => `Covers the payments for the ${esc(monthName(d.month).split(" ")[0])} payroll month, including the bills and statutory payments paid in early ${esc(monthName(shiftMonth(d.month, 1)).split(" ")[0])}.`;

// The head: Payments, the title, what the page is for with the company and its bank, the payroll month it covers; Excel and Print.
function budgetHead(d, actions) {
  const b = budgetBank(d);
  const xl = `/api/export/budget.xlsx?entity_id=${d.entity.id}&month=${d.month}&as_at=${esc(d.as_at)}`;
  return `<div class="pg-head bud-head"><div class="pg-words">
      <span class="eyebrow">Payments</span>
      <h1 id="pg-h1" tabindex="-1">Budget for ${esc(d.label)}${beforeTracking(d.entity, d.month) ? ` ${BEFORE_PILL}` : ""}</h1>
      <p class="bud-lede">The month's payments still to pay after the balance date, and the shortfall to request as funds. <b>${b.line}</b></p>
      <p class="bud-lede small">${cycleNote(d)}</p></div>
    ${actions ? `<div class="row noprint pg-actions"><a class="ghost" id="bud-excel" href="${xl}" download>${icon("download")}Excel</a>
      <button type="button" class="ghost" id="bud-print" data-bud-print="budget">${icon("printer")}Print budget</button></div>` : ""}</div>`;
}

// The figures the page and its print share: what the balance is, what is still to pay, the funds to request.
// A balance kept for another date than the page's is left out, here and in the print alike (budgetOther).
function budgetFigures(d) {
  const other = budgetOther(d);
  const balance = other ? null : d.balance, funds = other ? null : d.funds_to_request;
  const toPay = d.totals.MYR || 0;
  const rows = d.stored ? d.lines.filter(x => x.currency === "MYR" && !x.in_balance && x.to_pay != null) : d.to_pay.filter(p => p.currency === "MYR");
  const paid = d.stored ? d.lines.filter(x => x.currency === "MYR" && x.in_balance) : d.paid.filter(p => p.currency === "MYR");
  const paidSum = d.stored ? (d.in_balance.MYR || 0) : paid.reduce((a, p) => a + (p.amount || 0), 0);
  const noBal = balance == null || funds == null;
  const short = noBal ? null : funds > 0.005;
  return { other, balance, funds, toPay, nPay: rows.length, paidSum, nPaid: paid.length, noBal, short,
    left: noBal ? null : Math.round((balance - toPay) * 100) / 100,
    others: Object.entries(d.totals).filter(([cur]) => cur !== "MYR") };
}

function budgetPage(d, here, R) {
  const f = budgetFigures(d), b = budgetBank(d), eff = d.as_at, code = esc(d.entity.code);
  const noDate = d.stored && !f.other && d.balance != null && !d.saved_as_at;
  // A stored budget with no date kept shows an empty date box: today is never filled in unasked.
  const dateVal = d.stored && !d.saved_as_at && !here ? "" : eff;
  const tick = w => BUD.tick === w ? `<span class="ok-tick" id="bud-tick-${w}">${icon("check")}Saved</span>` : "";
  const notSet = !d.stored ? `<section class="banner warn noprint bud-notset">${icon("alert")}<div><b>Not set up yet</b>
      <div class="note">This list is worked out from the month's payments and can't be edited. ${d.previous ? `Setting it up copies ${esc(monthName(shiftMonth(d.month, -1)).split(" ")[0])}'s budget with its amounts, so each line can then be changed, added to and deleted.`
        : "Setting it up makes a line for each payment out, which you can then change, add to and delete."} The bank balance is kept with the budget, so it is entered once the budget is set up.</div></div>
      <button type="button" class="btn" id="bud-setup">Set up budget</button></section>` : "";
  const monthCard = d.set_up ? "" : notSetUp(d.entity, d.month, held(d));
  const balBox = `<section class="card noprint bud-bal" aria-labelledby="bud-bal-h">
      <div class="bud-bal-row">
        <div class="bud-bank"><span class="bud-plate" aria-hidden="true">${icon("bank")}</span><div><b id="bud-bal-h">Bank balance</b><div class="note">${b.sub}</div></div></div>
        <div class="field bud-f"><label for="bud-date">Bank balance as at${tick("date")}</label>
          <input id="bud-date" type="date" min="${R.first}" max="${R.last}" value="${esc(dateVal)}"></div>
        <div class="field bud-f"><label for="bud-bal">Bank balance (RM)${tick("bal")}</label>
          <input id="bud-bal" type="text" inputmode="decimal" autocomplete="off" class="num" placeholder="${f.balance == null ? "Not entered" : "10,000.00"}"
            value="${f.balance == null ? "" : esc(plainNum(f.balance, "MYR"))}"${d.stored ? "" : ` disabled aria-describedby="bud-bal-why"`}>
          ${d.stored ? "" : `<span class="note" id="bud-bal-why">Set up the budget to enter the balance: it is kept with the budget.</span>`}</div>
      </div>
      <div class="note">${d.stored ? "Both boxes save when you leave them or press Enter, and the figures below follow the date." : "The figures below follow the date."} A payment paid on or before the date is already out of the balance, so it is not counted as still to pay.</div>
      ${noDate ? `<div class="banner warn" role="status">${icon("calendar")}<span>Enter the date this balance was taken. Until then the budget is as at today, ${esc(shortDate(d.today))}.</span></div>` : ""}
      ${f.other ? `<div class="banner warn" role="status">${icon("calendar")}<span>As at ${eff === d.today ? "today, " : ""}${esc(shortDate(eff))}${here ? ", as Next up counts it" : ""}. The balance you entered is as at ${esc(shortDate(d.saved_as_at))}.</span>
        <button type="button" class="link" data-saved-balance="1">Use ${esc(shortDate(d.saved_as_at))}</button></div>` : ""}
    </section>`;
  const fundCard = f.noBal
    ? `<div class="stat bud-stat bud-funds" aria-live="polite"><span class="t">Funds to request</span><b class="v-words" id="bud-short">${f.other ? `Not worked out for ${esc(shortDate(d.as_at))}` : "Enter the bank balance to see funds to request"}</b>
        <span class="n">${f.other ? `The balance is for ${esc(shortDate(d.saved_as_at))}: open the budget as at that date to see funds to request.`
          : d.stored ? "Worked out once a balance and its date are entered." : "Set up the budget, then enter the balance and its date."}</span></div>`
    : f.short
      ? `<div class="stat bud-stat bud-funds bad" aria-live="polite"><span class="t">Shortfall to request</span><b class="v" id="bud-short">RM ${plainNum(f.funds, "MYR")}</b><span class="n">Fund requisition needed.</span>
          <div class="row tight noprint"><button type="button" class="btn small" id="bud-fund" data-bud-print="fund">${icon("printer")}Print fund request</button>
          <a class="ghost small" href="/api/export/budget.xlsx?entity_id=${d.entity.id}&month=${d.month}&as_at=${esc(eff)}" download>Excel</a></div></div>`
      : `<div class="stat bud-stat bud-funds ok" aria-live="polite"><span class="t">Covered by the balance</span><b class="v" id="bud-short">RM ${plainNum(f.left, "MYR")}</b><span class="n">Left over: no funds needed</span></div>`;
  const cards = `<div class="bud-stats noprint">
      <div class="stat bud-stat"><span class="t">Balance on ${esc(shortDate(eff))}</span><b class="v" id="bud-balance">${f.balance == null ? "Not entered" : money(f.balance)}</b>
        <span class="n">${f.balance != null ? (b.label ? esc(b.label) : code) : f.other ? `The saved balance is as at ${esc(shortDate(d.saved_as_at))}` : d.stored ? "No balance saved yet" : "Not set up yet"}</span></div>
      <div class="stat bud-stat"><span class="t">Still to pay after ${esc(shortDate(eff))}</span><b class="v" id="bud-total">${money(f.toPay)}</b><span class="n">${f.nPay} payment${f.nPay === 1 ? "" : "s"}</span></div>
      ${fundCard}
      <div class="stat bud-stat"><span class="t">Already paid (in the balance)</span><b class="v">${money(f.paidSum)}</b><span class="n">${f.nPaid} payment${f.nPaid === 1 ? "" : "s"} on or before ${esc(shortDate(eff))}</span></div>
      ${f.others.length ? `<div class="stat bud-stat" id="bud-other"><span class="t">Other currencies (not in the shortfall)</span><b class="v">${f.others.map(([cur, n]) => money(n, cur)).join(" · ")}</b><span class="n">Each currency on its own</span></div>` : ""}
    </div>`;
  const bvp = d.stored ? (() => {
    const s = d.sums.MYR || { budget: 0, paid_by: 0 }, usd = d.lines.filter(x => x.currency !== "MYR");
    const extra = Object.entries(usd.reduce((a, x) => (a[x.currency] = (a[x.currency] || 0) + (x.amount || 0), a), {})).map(([c, n]) => money(n, c)).join(", ");
    const items = [["Budgeted", money(s.budget) + (extra ? ` (and ${extra})` : "")], ["Paid against the budget", money(s.paid_by || 0)], ["Still to pay", money(f.toPay)]];
    if (!f.noBal) items.push(["Funds to request", f.short ? money(f.funds) : "None: covered by the balance"]);
    return `<section class="card noprint bud-bvp" aria-labelledby="bud-bvp-h"><div class="bud-bvp-t"><h2 id="bud-bvp-h">Budget vs paid</h2><span class="note">The same figures as the Overview card, as at ${esc(shortDate(eff))}</span></div>
      <dl>${items.map(([t, v]) => `<div><dt>${esc(t)}</dt><dd>${v}</dd></div>`).join("")}</dl>
      <span class="note small">Paid counts the payments on budget lines paid on or before ${esc(shortDate(eff))}. Already paid (in the balance) also counts paid payments that have no line, listed under Paid but not in the budget.</span></section>`;
  })() : "";
  const main = d.stored ? budgetLines(d) : budgetWorked(d);
  return `${budgetHead(d, true)}${monthCard}${notSet}${balBox}${cards}${bvp}
    <div class="bud-split"><div class="bud-main">${main}</div>
      <div class="bud-side noprint">${budgetPaidList(d)}
        <section class="card bud-help">${icon("help")}<p>An estimate whose bank lines so far add up to less (a fund requisition paid in tranches) is budgeted at the estimate until you confirm the amount in the payment.</p></section></div></div>`;
}
const held = d => d.stored ? d.lines.length : d.to_pay.length + d.paid.length;

// "Best done on a computer" (MobileDesktopOnly.dc.html), shown only at narrow widths: the table scrolls inside its frame.
const budgetPhone = () => desktopNote("Budget", "The budget is a wide grid of figures, easier to read and enter on a computer. The table scrolls sideways here.");

// The stored budget's lines: one table per currency, every figure a box that saves when you leave it.
function budgetLines(d) {
  const sel = BUD.sel;
  for (const id of [...sel]) if (!d.lines.some(x => x.id === id)) sel.delete(id);
  // Ringgit, the company's account currencies, and any line's own (an account stopped since keeps its lines shown).
  const addCurs = [...new Set(["MYR", ...(ent()?.accounts || []).map(a => a.currency)])];  // a line can be added in these
  const currencies = [...new Set([...addCurs, ...d.lines.map(x => x.currency)])];
  const shown = currencies.filter(c => c === "MYR" || d.lines.some(x => x.currency === c));
  BUD.visible = new Set();  // the lines shown now: Select all and Delete selected act on these only
  const diffPill = (diff, cur) => Math.abs(diff) <= 0.01 ? `<span class="pill ok">Matched</span>`
    : `<span class="pill ${diff < 0 ? "warn" : "bad"}">${diff < 0 ? "Under" : "Over"} by ${money(Math.abs(diff), cur)}</span>`;
  const row = (x, i) => {
    const no = i + 1, name = x.description || `line ${no}`;
    return `<tr data-line="${x.id}">
      <td class="noprint"><input type="checkbox" data-sel="${x.id}" aria-label="Select line ${no}, ${esc(name)}"${sel.has(x.id) ? " checked" : ""}></td><td class="bl-no">${no}</td>
      <td><input class="cell" id="bl-d-${x.id}" data-f="description" maxlength="200" autocomplete="off" value="${esc(x.description)}" aria-label="Description, line ${no}">
        ${x.in_balance ? `<div class="note">Paid ${shortDate(x.paid_date)}, already in the balance</div>` : ""}</td>
      <td><input class="cell" id="bl-k-${x.id}" data-f="details" maxlength="200" autocomplete="off" value="${esc(x.details)}" placeholder="Bank / details" aria-label="Bank or details, line ${no}"></td>
      <td class="num"><input class="cell amt num" id="bl-a-${x.id}" data-f="amount" inputmode="decimal" autocomplete="off" value="${x.amount == null ? "" : esc(plainNum(x.amount, x.currency))}" aria-label="Budget amount, line ${no}"></td>
      <td><div class="bl-paid"><b>${x.paid == null ? "—" : plainNum(x.paid, x.currency)}</b><span class="pill ${x.status.tone}">${esc(x.status.text)}</span></div></td>
      <td class="bl-pay noprint"><select class="cell" data-f="payment_id" aria-label="Linked payment, line ${no}"><option value="">Not linked</option>${d.payments.filter(p => p.currency === x.currency && (!p.line_id || p.line_id === x.id)).map(p =>
        `<option value="${p.id}"${p.id === x.payment_id ? " selected" : ""}>${esc(p.description)} · ${plainNum(p.amount, p.currency)} · ${p.paid_date ? "paid " + shortDate(p.paid_date) : "due " + shortDate(p.due_date)}</option>`).join("")}</select>
        <div class="note">${x.due_date ? fmtDate(x.due_date) : ""}</div></td>
      <td class="noprint"><div class="row tight bl-act"><button type="button" class="ghost small" data-hist-open="budget_lines:${x.id}" data-hist-title="${esc(x.description || `Line ${no}`)}" aria-label="History of line ${no}, ${esc(name)}">${icon("history")}History</button>
        <button type="button" class="ghost small icon-only" data-del="${x.id}" aria-label="Delete line ${no}, ${esc(name)}" title="Delete line">${icon("trash")}</button></div></td></tr>`;
  };
  const table = cur => {
    const list = d.lines.filter(x => x.currency === cur), sums = d.sums[cur] || { budget: 0, paid: 0, diff: 0 };
    const n = BUD.shown[cur] ?? BUD_STEP, vis = list.slice(0, n);  // each currency's table pages on its own
    vis.forEach(x => BUD.visible.add(x.id));
    return `<div class="bud-cur"><div class="bud-cur-h">${curTitle(cur)}${cur === "MYR" ? "" : ", not in the shortfall"}</div>
      <div class="tbl-wrap" role="region" aria-label="Budget lines in ${cur === "MYR" ? "ringgit" : esc(cur)}, scrolls" tabindex="0"><table class="bud-tbl">
      <thead><tr><th class="noprint"><span class="sr-only">Select</span></th><th>No.</th><th>Description</th><th>Bank / details</th><th class="num">${curHead(cur)} budget</th><th>Paid · against budget</th><th class="noprint">Payment · date</th><th class="noprint"><span class="sr-only">Actions</span></th></tr></thead><tbody>
      ${vis.map((x, i) => row(x, i)).join("") || `<tr><td class="noprint"></td><td colspan="7" class="muted">No lines.</td></tr>`}
      <tr class="tot"><td class="noprint"></td><td></td><td>TOTAL</td><td></td><td class="num">${plainNum(sums.budget, cur)}</td>
      <td><div class="bl-paid"><span>${list.some(x => x.paid != null) ? plainNum(sums.paid, cur) : "—"}</span>${list.some(x => x.paid != null) ? diffPill(sums.diff, cur) : ""}</div></td><td class="noprint"></td><td class="noprint"></td></tr></tbody></table></div>
      ${manyRows({ shown: vis.length, total: list.length > BUD_STEP ? list.length : 0, what: cur === "MYR" ? "lines" : `${esc(cur)} lines`, attr: "data-bud-more", value: cur })}</div>`;
  };
  const tables = shown.map(table).join("");  // first, so the lines shown are known for Select all
  const picked = [...sel].filter(id => BUD.visible.has(id)).length;
  const unlinked = d.lines.filter(x => !x.payment_id).length;
  const nib = d.not_in_budget;
  return `<section class="card bud-lines" aria-labelledby="bud-lines-h">
      <div class="bud-lines-top noprint"><div><h2 id="bud-lines-h" tabindex="-1">Budget lines</h2><div class="note">Change any figure, description or detail here; it saves when you leave the box. The payments themselves are not changed.</div></div>
        <div class="row tight"><label class="bud-all"><input type="checkbox" id="bud-all"${BUD.visible.size && picked === BUD.visible.size ? " checked" : ""}> Select all</label>
          <button type="button" class="ghost small" id="bud-delsel"${picked ? "" : " disabled"}>Delete selected${picked ? ` (${picked})` : ""}</button>
          ${addCurs.map(cur => `<button type="button" class="btn small" data-add="${esc(cur)}" aria-label="Add a blank line${addCurs.length > 1 ? ` in ${cur === "MYR" ? "ringgit" : esc(cur)}` : ""}">${icon("plus")}Add line${addCurs.length > 1 ? ` (${curHead(cur)})` : ""}</button>`).join("")}</div></div>
      ${unlinked ? `<div class="bud-unlinked noprint">${unlinked} line${unlinked === 1 ? " is" : "s are"} not linked to a payment, so ${unlinked === 1 ? "it shows" : "they show"} Not paid yet. Link them in the Payment column or delete the ones you do not need.</div>` : ""}
      ${budgetPhone()}
      ${tables}
      <div class="bud-foot noprint">${icon("printer")}<span>Print budget puts these tables in light colours, without the sidebar, the buttons and the Payment picker. The paid figures and status are not printed; each line's due date is.</span></div>
    </section>
    <section class="card noprint bud-nib" aria-labelledby="bud-nib-h"><div class="bud-sec-h">${icon("alert")}<h2 id="bud-nib-h">Paid but not in the budget</h2></div>
      ${nib.length ? `<div class="note">This month's payments with no line above, paid or still to pay.</div><div class="tbl-wrap"><table><thead><tr><th>Description</th><th class="num">Amount</th><th>Paid on</th><th><span class="sr-only">Action</span></th></tr></thead><tbody>
        ${nib.map(p => `<tr><td>${esc(p.description)}</td><td class="num">${money(p.amount, p.currency)}</td><td>${p.paid_date ? fmtDate(p.paid_date) : "Not paid yet"}</td>
        <td class="num"><button type="button" class="ghost small" data-add-payment="${p.id}" aria-label="Add ${esc(p.description)} to the budget">Add to budget</button></td></tr>`).join("")}</tbody></table></div>`
        : `<div class="note">Every payment for this month is on a line.</div>`}</section>
    ${(() => { const ch = budgetChart(d); return ch ? `<section class="card noprint bud-chart" aria-labelledby="bud-chart-h"><div class="bud-sec-h">${icon("chart")}<h2 id="bud-chart-h">Budget against paid</h2></div>${ch}</section>` : ""; })()}`;
}

// No stored budget: what is still to pay after the balance date, worked out from the payments, one table per currency. Read only.
function budgetWorked(d) {
  const byCur = {};
  for (const p of d.to_pay) (byCur[p.currency] ||= []).push(p);
  // due is what the row is budgeted at (an estimate the bank lines linked so far fall short of until the amount is
  // confirmed; what the lines add up to when a note accepts the difference), so due less to_pay was paid by the date.
  const note = p => {
    const full = p.due;
    if (full != null && full - p.to_pay > 0.005) return p.estimate != null
      ? `<div class="note">${money(full - p.to_pay, p.currency)} of the ${plainNum(full, p.currency)} estimated was paid by ${shortDate(d.as_at)}; the rest is budgeted until you confirm the amount in the payment</div>`
      : `<div class="note">${money(full - p.to_pay, p.currency)} of ${plainNum(full, p.currency)} paid by ${shortDate(d.as_at)}; the rest is budgeted</div>`;
    return p.paid_date > d.as_at ? `<div class="note">Paid ${shortDate(p.paid_date)}, after the balance date</div>` : "";
  };
  const tables = Object.entries(byCur).map(([cur, list]) => `<div class="bud-cur"><div class="bud-cur-h">${curTitle(cur)}${cur === "MYR" ? "" : " · not in the shortfall"}</div>
      <div class="tbl-wrap"><table><thead><tr><th>No.</th><th>Description (EST)</th><th class="num">${curHead(cur)}</th><th>Payment on</th></tr></thead><tbody>
      ${list.map((p, i) => `<tr><td>${i + 1}</td><td>${esc(p.description)}${p.amount_is_estimate || p.estimate != null ? " · EST" : ""}${note(p)}${p.bank_details ? `<div class="note mono">${esc(p.bank_details)}</div>` : ""}</td><td class="num">${plainNum(p.to_pay, cur)}</td><td>${fmtDate(p.due_date)}</td></tr>`).join("")}
      <tr class="tot"><td></td><td>TOTAL</td><td class="num">${plainNum(d.totals[cur], cur)}</td><td></td></tr></tbody></table></div></div>`).join("");
  return `<section class="card bud-lines" aria-labelledby="bud-lines-h"><div class="bud-lines-top noprint"><div><h2 id="bud-lines-h" tabindex="-1">Still to pay after ${esc(shortDate(d.as_at))}</h2>
      <div class="note">Read only. Change amounts in the Payments register; EST marks amounts not confirmed yet.</div></div></div>
    ${tables ? budgetPhone() + tables : `<div class="list-empty">${emptyState({ glyph: "check", tone: "ok", compact: true, title: d.paid.length ? `Nothing left to pay after ${fmtDate(d.as_at)}.` : "No payments planned." })}</div>`}</section>`;
}

// Already paid (in the balance): the payments paid on or before the date, folded away on a button.
function budgetPaidList(d) {
  const list = d.stored ? d.lines.filter(x => x.in_balance).map(x => ({ name: x.description, date: x.paid_date, amount: x.amount, currency: x.currency }))
    : d.paid.map(p => ({ name: p.description, date: p.paid_date, amount: p.amount, currency: p.currency }));
  list.sort((a, b) => (a.date || "") < (b.date || "") ? -1 : 1);
  const totals = {};
  for (const p of list) totals[p.currency] = (totals[p.currency] || 0) + (p.amount || 0);
  const open = BUD.paidOpen;
  return `<section class="card bud-paid"><button type="button" class="bud-paid-btn" id="bud-paid-btn" data-bud-paid="1" aria-expanded="${open}">${icon("check")}<span>Already paid (in the balance)</span>
      <span class="muted">${Object.entries(totals).map(([c, n]) => money(n, c)).join(" · ") || money(0)}</span><span class="chev${open ? " on" : ""}">${icon("chevronRight")}</span></button>
    ${open ? `<div class="bud-paid-list">${list.map(p => `<div><span>${esc(p.name)} <span class="muted">· ${esc(shortDate(p.date))}</span></span><b>${money(p.amount, p.currency)}</b></div>`).join("")
      || `<div class="muted">Nothing paid on or before ${esc(shortDate(d.as_at))}.</div>`}</div>` : ""}</section>`;
}

// The print preview: the budget, or the fund request (only while there is a shortfall to request). Printing always uses light
// colours and leaves out the menu, the top bar, the buttons and this note.
function budgetPrint(d, kind) {
  const f = budgetFigures(d), b = budgetBank(d), eff = d.as_at, fund = kind === "fund" && f.short;
  const label = f.noBal ? "Funds to request" : f.short ? "Shortfall = fund requisition needed" : "Covered, left over";
  const value = f.other ? `not worked out: the balance is for ${shortDate(d.saved_as_at)}; open the budget as at that date to see funds to request`
    : f.noBal ? "not worked out, bank balance not entered" : f.short ? money(f.funds) : money(f.left);
  // The budget print lists every line at its budget (as Budget.dc.html prints it); the fund request lists only what is still
  // to pay, at what is left of it, so its total is the Still to pay figure above it.
  const stillToPay = fund || !d.stored;
  const lines = cur => d.stored && !fund ? d.lines.filter(x => x.currency === cur).map((x, i) => [i + 1, x.description, x.details || "", x.amount || 0, x.due_date])
    : d.stored ? d.lines.filter(x => x.currency === cur && !x.in_balance && x.to_pay > 0).map((x, i) => [i + 1, x.description, x.details || "", x.to_pay, x.due_date])
    : d.to_pay.filter(p => p.currency === cur).map((p, i) => [i + 1, p.description + (p.amount_is_estimate || p.estimate != null ? " (EST)" : ""), p.bank_details || "", p.to_pay || 0, p.due_date]);
  const curs = [...new Set(["MYR", ...(d.stored ? d.lines : d.to_pay).map(x => x.currency)])].filter(c => c === "MYR" || !fund);
  const tables = curs.map(cur => {
    const rows = lines(cur);
    if (!rows.length && cur !== "MYR") return "";
    const tot = stillToPay ? (d.totals[cur] || 0) : rows.reduce((a, r) => a + r[3], 0);
    return `<div class="sheet-t"><div class="sheet-th">${curTitle(cur)}${cur === "MYR" ? "" : ", not in the shortfall"}</div><table>
      <thead><tr><th>No.</th><th>Description</th><th>Details</th><th class="num">${curHead(cur)} ${stillToPay ? "still to pay" : "budget"}</th><th>Due date</th></tr></thead><tbody>
      ${rows.map(r => `<tr><td>${r[0]}</td><td>${esc(r[1])}</td><td>${esc(r[2])}</td><td class="num">${plainNum(r[3], cur)}</td><td>${r[4] ? esc(shortDate(r[4])) : "—"}</td></tr>`).join("")}
      <tr class="tot"><td></td><td>TOTAL</td><td></td><td class="num">${plainNum(tot, cur)}</td><td></td></tr></tbody></table></div>`;
  }).join("");
  return `<div class="bud-preview">
    <div class="bud-preview-top noprint"><div><span class="eyebrow">Print preview</span><h1 id="bud-print-h" tabindex="-1">${fund ? "Print fund request" : "Print budget"}</h1></div>
      <div class="row tight"><button type="button" class="ghost" id="bud-print-back">Back to budget</button><button type="button" class="btn" id="bud-print-go">${icon("printer")}Print</button></div></div>
    <p class="note noprint">Printing always uses light colours. The menu, the top bar, the buttons and this note are left out, and the Payment picker, the paid figures, the status and the row buttons are not printed. Each line's due date is.</p>
    <div class="sheet">
      <div class="sheet-head"><div><div class="sheet-co">${b.line}</div><div class="sheet-title">${fund ? "Fund request" : "Budget"} for ${esc(d.label)}</div></div><div class="sheet-at">As at ${esc(fmtDate(eff))}</div></div>
      <div class="sheet-figs"><span>Bank balance${b.label ? ` (${esc(b.label)})` : ""}: <b>${f.other ? `not entered for ${esc(shortDate(eff))}` : f.balance == null ? "not entered" : money(f.balance)}</b></span>
        <span>Still to pay: <b>${money(f.toPay)}</b></span><span>${label}: <b>${esc(value)}</b></span></div>
      ${tables}
      <div class="sheet-foot">Prepared ${esc(fmtDate(d.today))}. Figures as at ${esc(fmtDate(eff))}.</div>
    </div></div>`;
}
