"use strict";
/* ---------------- Payroll check (hrp/payrollcheck.py) ---------------- */
// The month's payroll workbook, checked before paying: upload it, read the headline, then what to fix per person and
// for the Summary with the cells, and the month's amounts to pay. A corrected file is checked again from the same box;
// the earlier checks stay listed. IC numbers come from the server masked (all but the last 4).
const PC_TONE = { fix: "bad", check: "warn", note: "grey" };
const sen2rm = n => money(n == null ? null : n / 100);
const pcTone = c => c.fix || c.to_fix ? "bad" : c.check || c.to_check ? "warn" : "ok";
async function viewPayroll(main, checkId) {
  const r = await api(`/api/payroll-check?entity_id=${state.entity}&month=${state.month}${checkId ? `&check=${checkId}` : ""}`);
  const ch = r.chosen, rep = ch?.report;
  const where = r.task ? `It is filed as the month's payroll summary on the checklist item ${esc(r.task.title)}.`
    : `${esc(r.label)} isn't set up for ${esc(r.entity.code)}, so the workbook is kept but not filed on a checklist item.`;
  const upload = `<form class="row" id="pcForm"><label class="field"><span>${ch ? "Corrected workbook (.xlsx)" : "Payroll workbook (.xlsx)"}</span>
      <input id="pcFile" type="file" accept=".xlsx"></label><button class="btn" type="submit">${ch ? "Check again" : "Check the workbook"}</button></form>
    <div class="note">Upload ${esc(r.label)}'s workbook before paying. ${where} Statutory rates as at ${esc(r.rates_as_at)}; PCB amounts themselves are not checked.</div>`;
  const finding = f => `<div class="pc-f"><div class="row tight"><span class="pill ${PC_TONE[f.severity]}">${esc(f.severity_label)}</span>
      ${f.cells.length ? `<span class="mono">${esc(f.sheet ? f.sheet + " " : "")}${esc(f.cells.join(", "))}</span>` : f.sheet ? `<span class="mono">${esc(f.sheet)}</span>` : ""}</div>
    <div>${esc(f.what)}</div><div class="note">Should be: ${esc(f.should)}</div></div>`;
  const group = g => !g.findings.length && !g.lines.length ? "" : `<div class="pc-g"><h3>${esc(g.title)}${g.nric ? ` <span class="muted mono">${esc(g.nric)}</span>` : ""}${g.findings.length ? "" : ` <span class="pill ok">Nothing found</span>`}</h3>
    ${g.findings.map(finding).join("")}${g.lines.length ? `<div class="note">${g.lines.map(esc).join("<br>")}</div>` : ""}</div>`;
  const pay = rep ? `<div class="card"><h2>Amounts to pay · as the Summary has them</h2><div class="tbl-wrap"><table><thead><tr><th>Name</th><th>NRIC</th><th class="num">To pay</th>
      ${rep.pay.authorities.map(a => `<th class="num">${esc(a)}</th>`).join("")}</tr></thead><tbody>
      ${rep.pay.people.map(p => `<tr><td>${esc(p.name)}</td><td class="mono">${esc(p.nric)}</td><td class="num">${sen2rm(p.to_pay)}</td>${rep.pay.authorities.map(a => `<td class="num">${sen2rm(p[a])}</td>`).join("")}</tr>`).join("")}
      <tr><td><b>Total</b></td><td></td><td class="num"><b>${sen2rm(rep.pay.totals.to_pay)}</b></td>${rep.pay.authorities.map(a => `<td class="num"><b>${sen2rm(rep.pay.totals[a])}</b></td>`).join("")}</tr>
      </tbody></table></div><div class="note">KWSP, SOCSO and EIS are the employee's and employer's shares together, rounded to the sen. Fix what the check found before paying from this.</div></div>` : "";
  const earlier = r.checks.length > 1 || (ch && !ch.latest) ? `<div class="card"><h2>Checks of ${esc(r.label)}</h2>${r.checks.map((x, i) => `<div class="row spread"><span>${i ? "Earlier version" : "Latest"} · ${esc(x.filename)} · <span class="muted">${esc(x.checked_at.replace("T", " "))}</span></span>
      <span class="row tight"><span class="pill ${pcTone(x)}">${esc(x.headline)}</span>${ch && x.id === ch.id ? `<span class="muted">Shown</span>` : `<button class="ghost small" type="button" data-pc-show="${x.id}">Show</button>`}</span></div>`).join("")}</div>` : "";
  main.innerHTML = `${entityPicker()}
    <div class="card"><div class="row spread"><h1>Payroll check · ${esc(r.entity.code)} · ${esc(r.label)}</h1>
      ${ch ? `<a class="ghost" href="/api/payroll-check/export.xlsx?entity_id=${state.entity}&month=${state.month}&check=${ch.id}">Excel report</a>` : ""}</div>
      ${upload}
      ${rep ? `<div class="row"><span class="pill ${pcTone(rep.counts)}">${esc(rep.headline)}</span>
        <span class="note">${ch.latest ? "Latest check" : "An earlier version"}: ${esc(ch.filename)}, ${esc(ch.checked_at.replace("T", " "))}</span></div>` : `<div class="note">No workbook checked for ${esc(r.label)} yet.</div>`}</div>
    ${rep ? `<div class="card">${rep.groups.map(group).join("")}</div>` : ""}
    ${pay}${earlier}`;
  $("#pcForm").onsubmit = async ev => {
    ev.preventDefault();
    const f = $("#pcFile").files[0];
    if (!f) return toast("Choose the payroll workbook first.", true);
    const fd = new FormData(); fd.append("file", f); fd.append("entity_id", state.entity); fd.append("month", state.month);
    try { const out = await api("/api/payroll-check", { form: fd }); toast(out.chosen?.report?.headline || "Checked"); await viewPayroll(main); }
    catch (e) { toast(e.message, true); }
  };
  main.querySelectorAll("[data-pc-show]").forEach(b => b.onclick = () => viewPayroll(main, +b.dataset.pcShow).catch(e => toast(e.message, true)));
}

