"use strict";
/* ---------------- Audit pack ---------------- */
// Before you print: what the month still needs, as the server works it out, under these headings. Each line is a button
// to the screen that fixes it.
const READY_HEADS = { statement: "Bank statements", lines: "Bank statements", payment: "Payments not complete",
  task: "Checklist documents missing", task_open: "Checklist items not done", not_in_sql: "Paid, not recorded in SQL",
  unprintable: "Files that won't print" };

async function viewAudit(main) { return pageDraw("main", page => auditDraw(page, main)); }
async function auditDraw(page, main) {
  const r = await page.read(api(`/api/audit-readiness?entity_id=${state.entity}&month=${state.month}`));
  const setUp = r.set_up ? "" : notSetUp(r.entity, r.month, r.payments);
  if (!r.set_up && !r.payments) { main.innerHTML = entityPicker() + setUp; return; }
  const packs = await page.read(api(`/api/audit-packs?entity=${state.entity}&month=${state.month}`));
  let head = "";
  const open = r.items.map(x => `${READY_HEADS[x.kind] !== head ? `<h3>${esc(head = READY_HEADS[x.kind])}</h3>` : ""}
    <button class="fix" data-fix="${x.fix}" data-id="${x.id ?? ""}"><b>${esc(x.title)}</b><span>${esc(x.detail)}</span></button>`).join("");
  const pack = !r.pack ? "" : r.pack.changed ? `<div class="row"><span class="pill warn">${esc(r.pack_open)}</span><span class="note">Build it again before you print.</span></div>`
    : `<div class="note">The pack built ${esc(r.pack.when)} is up to date.</div>`;
  // With a pack built and up to date, it asks whether it was printed and filed (a month set up can be marked).
  const built = r.pack && !r.pack.changed && r.set_up && !r.closed_at;
  // What the pack doesn't hold: the SQL vouchers that stand for an upload are printed from SQL.
  const fromSql = r.to_print ? `<div class="note">Not in the PDF: print ${esc(r.to_print)} from SQL.</div>` : "";
  main.innerHTML = `${entityPicker()}${setUp}
    <div class="card"><div class="row spread"><h1>Audit pack · ${esc(r.entity.code)} · ${esc(r.label)}</h1>${r.closed_at ? `<span class="pill ok">Filed ${shortDate(r.closed_at)}</span>` : ""}</div>
      <div class="note">One PDF with an index page, then every payment's documents in filing order (PV, approval, invoice, bank receipt, e-Invoice), then checklist documents and the bank statement. Print it once and file it.</div>
      <h2>Before you print</h2>
      ${r.ready ? `<div class="row"><span class="pill ok">Ready to print</span><span class="note">Every bank statement is imported and explained, every payment and checklist item is done with its documents, and every file will print.</span></div>`
        : `<div class="row">${r.summary.map(s => `<span class="pill warn">${esc(s)}</span>`).join("")}</div>
          <div class="note">Click a line to fix it. You can still build the pack: what is missing is listed on its index page.</div><div class="fixes">${open}</div>`}
      ${fromSql}${pack}
      <div class="row"><button class="btn" id="buildPack">Build audit pack PDF</button>
        <a class="ghost" id="excelReport" href="/api/export/month.xlsx?entity_id=${state.entity}&month=${state.month}">Excel report</a>
        <button class="ghost" id="auditorPack">Auditor package</button></div><div id="packOut" class="note" hidden></div>
      ${built ? `<div class="row"><b>Printed and filed?</b><button class="btn" data-close-month="built">Yes, mark month as filed</button></div>` : ""}</div>
    <div class="card"><h2>Recent packs</h2>${packs.length ? packs.map(packRow).join("") : `<div class="note">None built for ${esc(r.label)} yet.</div>`}</div>`;
}

// A pack built for the month: its file (or that it has gone), when, and Check this pack (by its trail row, or by its
// file for one built before the trail recorded packs).
const packRow = p => `<div class="row spread"><span>${p.url ? `<a href="${esc(p.url)}" target="_blank">${esc(p.name)}</a>` : esc(p.name)}${p.missing ? ` <span class="pill bad">File missing</span>` : ""}${p.via ? ` <span class="muted">· for the ${esc(p.via)}</span>` : ""}</span>
  <span class="row tight"><span class="muted">${esc(p.at.replace("T", " "))}</span><button class="ghost small" type="button" data-pack-check="${esc(p.event ?? "")}" data-pack-file="${esc(p.name)}">Check this pack</button></span></div>`;

