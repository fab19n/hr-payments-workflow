"use strict";
/* ---------------- Overview ---------------- */
async function viewOverview(main) {
  const asAt = state.meta.entities.map(e => [e.id, storedAsAt(e.id, state.month)]).filter(([, d]) => d).map(([id, d]) => `&as_at_${id}=${d}`).join("");
  const [ov, next] = await Promise.all([api(`/api/overview?month=${state.month}${asAt}`), loadNext(null)]);
  const cards = ov.entities.map(x => {
    const budget = (cur, n) => `<div class="stat"><b class="mono">${Math.round(n).toLocaleString("en-MY")}</b><span>budget as at ${shortDate(x.budget_as_at)} (${cur === "MYR" ? "RM" : esc(cur)})</span></div>`;
    if (!x.set_up && !x.payments && !x.tasks) return notSetUp(x.entity, ov.month);
    // The bar counts payments out; money received has its own figure beside it.
    const outAll = x.payments - x.receipts.payments, outDone = x.complete - x.receipts.complete;
    const pct = outAll ? Math.round(outDone / outAll * 100) : 0;
    // Each count is a button to what it counts (pillGo).
    const flags = [], kept = [], count = (kind, tone, text, stays) => {
      const pill = `<button class="pillbtn" data-pill="${kind}" data-entity="${x.entity.id}" title="Show these"><span class="pill ${tone}">${text}</span></button>`;
      flags.push(pill);
      if (stays) kept.push(pill);  // still shown in a month before the first month tracked (below)
    };
    if (x.overdue_tasks) count("overdue_tasks", "bad", `${x.overdue_tasks} checklist overdue`);
    if (x.due_today_tasks) count("due_today_tasks", "warn", `${x.due_today_tasks} checklist due today`);
    for (const f of x.payment_flags) count(f.way === "in" ? `in-${f.code}` : f.code, f.tone, `${f.n} ${f.way === "in" ? "receipt" : "payment"}${f.n > 1 ? "s" : ""} ${esc(lowerFirst(f.text))}`, true);
    if (x.part_paid) count("part_paid", "warn", `${x.part_paid} part paid`);
    if (x.receipts.part_paid) count("in-part_paid", "warn", `${x.receipts.part_paid} part received`);
    if (x.paid_missing) count("paid_missing", "warn", `${x.paid_missing} paid, documents missing`);
    if (x.receipts.paid_missing) count("paid_missing", "warn", `${x.receipts.paid_missing} received, documents missing`);
    if (x.unmatched_lines) count("unmatched_lines", "warn", `${x.unmatched_lines} bank lines not explained`, true);
    if (x.not_in_sql) count("not_in_sql", "warn", `${x.not_in_sql} paid, not recorded in SQL`);
    // A month filed is done with: the server counts nothing in it as to do. A month before the first month tracked
    // isn't tracked here (no checklist or SQL counts, green is for what is done), so it shows its grey pill with only
    // what still needs doing there: the bank lines to explain and the payments recorded in it.
    if (x.before_first) flags.splice(0, flags.length, BEFORE_PILL, ...kept);
    if (!flags.length) flags.push(x.closed_at ? `<span class="pill ok">Filed ${shortDate(x.closed_at)}</span>` : `<span class="pill ok">Nothing overdue</span>`);
    if (!x.set_up && !x.before_first) flags.push(`<span class="pill grey">Month not set up</span>`);
    return `<div class="card">
      <div class="row spread"><div><div class="eyebrow">${esc(x.entity.code)}</div><h2>${esc(x.entity.name)}</h2></div>
      <button class="btn small" data-view="entity" data-entity="${x.entity.id}">Open ${esc(x.entity.code)}</button></div>
      <div class="stats">
        <div class="stat"><b>${x.tasks_done}/${x.tasks}</b><span>checklist done</span></div>
        <div class="stat"><b>${outDone}/${outAll}</b><span>payments fully documented</span></div>
        ${x.receipts.payments ? `<div class="stat"><b>${x.receipts.complete}/${x.receipts.payments}</b><span>receipts fully documented</span></div>` : ""}
        <div class="stat"><b>${x.planned - x.receipts.planned}</b><span>not paid yet</span></div>
        ${x.receipts.payments ? `<div class="stat"><b>${x.receipts.planned}</b><span>not received yet</span></div>` : ""}
        ${budget("MYR", x.budget.MYR || 0)}${Object.entries(x.budget).filter(([cur]) => cur !== "MYR").map(([cur, n]) => budget(cur, n)).join("")}
      </div>
      <div class="bar"><i style="width:${pct}%"></i></div>
      <div class="row">${flags.join("")}</div>
    </div>`;
  }).join("");
  main.innerHTML = `
    <div id="nextUp">${nextCard(next, null)}</div>
    <div><div class="eyebrow">Payroll month</div><h1>${esc(ov.label)} cycle</h1>
    <div class="note">Covers the payroll month's checklist and payments, including the bills and statutory payments paid early in the next month. Each item's due date is set in Setup › Monthly checklist.</div></div>
    <div class="grid2">${cards}</div>
    <div class="card"><h2>How a payment is completed</h2>
      <div class="row"><span class="pill grey">Not paid</span> → <span class="pill warn">Paid, documents missing</span> → <span class="pill ok">Complete</span></div>
      <div class="note">A payment becomes <b>Paid</b> when you enter the paid date or its bank statement line is matched. It becomes <b>Complete</b> when every required document is uploaded, or already shown by a linked SQL voucher, a validated e-Invoice or its bank statement line. Only complete payments are ready to file.</div>
      <div class="note">Past its due date and not paid yet, a payment says why: <b>Not on Oct statement</b> (or the month it fell due in) once that month's bank statement is imported without it; until then <b>Waiting for SQL record</b> while SQL isn't imported up to its due date, or else <b>Waiting for Oct statement</b>. A statutory payment not paid by the 15th of the next month shows <b>Past legal deadline</b>.</div>
      <div class="note">If the bank lines matched add up to less than the amount, it shows <b>Part paid</b> until the rest is matched, or you note why in the payment (e.g. balance paid in October).</div>
      <div class="note">Money received (a tenant's rent, say) is set up on the Recurring page as <b>Money in</b>. It shows <b>Not received yet</b> until it is due, then <b>Waiting for Nov statement</b> or <b>Not on Nov statement</b> in the same way, and <b>Received 14 Nov</b> once a bank credit is matched or you enter the date. It is counted apart from the payments, and is never in the Budget.</div>
    </div>`;
}

