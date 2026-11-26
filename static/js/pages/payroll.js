"use strict";
/* ---------------- HR › Payroll › Workbook check (hrp/payrollcheck.py) ---------------- */
// The month's payroll workbook, checked before paying (PayrollCheck.dc.html): upload it, read the headline, then what to
// fix per person and for the Summary with the cells, and the month's amounts to pay. A corrected file is checked again
// from the same box; the earlier checks stay listed. IC numbers come from the server masked (all but the last 4).
// Only the Workbook check tab exists until payroll runs in this app (slice 15 adds the run tabs).
const PC_TONE = { fix: ["bad", "alert", "Fix before paying"], check: ["warn", "eye", "Check"], note: ["grey", "help", "Note"] };
const PC_HEAD = { fix: ["bad", "alert"], check: ["warn", "eye"], ok: ["ok", "verified"] };
const sen2rm = n => money(n == null ? null : n / 100);
const pcTone = c => c.fix || c.to_fix ? "bad" : c.check || c.to_check ? "warn" : "ok";
const pcKey = c => c.fix ? "fix" : c.check ? "check" : "ok";
const pcWhen = at => esc(String(at || "").replace("T", " "));
async function viewPayroll(main, checkId) { return pageDraw("main", page => payrollDraw(page, main, checkId)); }
async function payrollDraw(page, main, checkId) {
  const still = pageHere();  // the company and month this page is of
  const r = await page.read(api(`/api/payroll-check?entity_id=${state.entity}&month=${state.month}${checkId ? `&check=${checkId}` : ""}`));
  const ch = r.chosen, rep = ch?.report, code = esc(r.entity.code), label = esc(r.label);
  const f = rep && state.pcFilter && rep.counts[state.pcFilter] ? state.pcFilter : "all";
  const where = r.task ? `It is filed as the month's payroll summary on the checklist item <b>${esc(r.task.title)}</b>.`
    : `${label} isn't set up for ${code}, so the workbook is kept but not filed on a checklist item.`;
  const upload = `<form class="row" id="pcForm"><label class="field"><span>${ch ? "Corrected workbook (.xlsx)" : "Payroll workbook (.xlsx)"}</span>
      <input id="pcFile" type="file" accept=".xlsx"></label><button class="btn" type="submit" id="pcGo">${ch ? "Check again" : "Check the workbook"}</button></form>
    <div id="pcRefused"></div>
    <div class="note">Upload ${label}'s workbook before paying. ${where} Statutory rates as at ${esc(r.rates_as_at)}; PCB amounts themselves are not checked.</div>`;
  const finding = x => `<div class="pc-f"><div class="row tight"><span class="pill ${PC_TONE[x.severity][0]}">${icon(PC_TONE[x.severity][1])}${esc(x.severity_label)}</span>
      ${x.cells.length ? `<span class="mono">${esc(x.sheet ? x.sheet + " " : "")}${esc(x.cells.join(", "))}</span>` : x.sheet ? `<span class="mono">${esc(x.sheet)}</span>` : ""}</div>
    <div>${esc(x.what)}</div><div class="note">Should be: ${esc(x.should)}</div></div>`;
  const group = g => {
    const list = g.findings.filter(x => f === "all" || x.severity === f), lines = f === "all" ? g.lines : [];
    if (!g.findings.length && !g.lines.length) return "";
    if (f !== "all" && !list.length) return "";
    const nric = g.nric ? ` <span class="muted mono" aria-label="NRIC ending ${esc(String(g.nric).slice(-4))}">${esc(g.nric)}</span>` : "";
    return `<div class="pc-g"><h3>${esc(g.title)}${nric}${g.findings.length ? "" : ` <span class="pill ok">Nothing found</span>`}</h3>
      ${list.map(finding).join("")}${lines.length ? `<div class="note">${lines.map(esc).join("<br>")}</div>` : ""}</div>`;
  };
  const head = rep ? (() => {
    const [tone, glyph] = PC_HEAD[pcKey(rep.counts)];
    const fix = rep.counts.fix, next = ch.latest && fix
      ? `<div class="note">Next up on the <a href="${addrOf({ view: "overview", entity: "all", month: state.month }) || "#/"}">Overview</a> says "${esc(monthName(state.month).slice(0, 3))} ${code}: the payroll check found ${fix} thing${fix > 1 ? "s" : ""} to fix before paying" until a newer check of ${label} has nothing to fix.</div>` : "";
    return `<div class="banner ${tone}" id="pc-head" tabindex="-1">${icon(glyph)}<div><b>${esc(rep.headline)}</b>
      <span>${ch.latest ? "Latest check" : "An earlier version"}: ${esc(ch.filename)}, ${pcWhen(ch.checked_at)}</span></div></div>${next}`;
  })() : `<div class="pc-none"><b>No workbook checked for ${label} yet.</b>
      <div class="note">Choose the workbook above and check it before paying: what to fix, what to check and the amounts to pay show here.</div></div>`;
  const chips = rep ? (() => {
    const c = rep.counts, all = (c.fix || 0) + (c.check || 0) + (c.note || 0);
    const chip = (k, l, n) => `<button type="button" class="chip pc-chip${f === k ? " on" : ""}" aria-pressed="${f === k}" data-pc-filter="${k}">${l} <b>${n}</b></button>`;
    return `<h3 id="pc-f-h">What the check found</h3><div class="row tight" role="group" aria-label="Show findings">${chip("all", "All", all)}${chip("fix", "Fix before paying", c.fix || 0)}${chip("check", "Check", c.check || 0)}${chip("note", "Note", c.note || 0)}</div>`;
  })() : "";
  const groups = rep ? rep.groups.map(group).join("") : "";
  const noMatch = rep && f !== "all" && !groups
    ? `<div class="note">Nothing in this check is marked ${esc(PC_TONE[f][2])}. <button type="button" class="ghost small" data-pc-filter="all">Show everything</button></div>` : "";
  const pay = rep ? `<div class="card"><h2>Amounts to pay · as the Summary has them</h2><div class="tbl-wrap"><table aria-label="Amounts to pay for ${label}, per person and per authority, from the Summary sheet"><thead><tr><th>Name</th><th>NRIC</th><th class="num">To pay</th>
      ${rep.pay.authorities.map(a => `<th class="num">${esc(a)}</th>`).join("")}</tr></thead><tbody>
      ${rep.pay.people.map(p => `<tr><td>${esc(p.name)}</td><td class="mono">${esc(p.nric)}</td><td class="num">${sen2rm(p.to_pay)}</td>${rep.pay.authorities.map(a => `<td class="num">${sen2rm(p[a])}</td>`).join("")}</tr>`).join("")}
      <tr><td><b>Total</b></td><td></td><td class="num"><b>${sen2rm(rep.pay.totals.to_pay)}</b></td>${rep.pay.authorities.map(a => `<td class="num"><b>${sen2rm(rep.pay.totals[a])}</b></td>`).join("")}</tr>
      </tbody></table></div><div class="note">KWSP, SOCSO and EIS are the employee's and employer's shares together, rounded to the sen. Fix what the check found before paying from this.</div></div>` : "";
  const earlier = r.checks.length > 1 || (ch && !ch.latest) ? `<div class="card"><h2>Checks of ${label}</h2>${r.checks.map((x, i) => `<div class="row spread"><span>${i ? "Earlier version" : "Latest"} · ${esc(x.filename)} · <span class="muted">${pcWhen(x.checked_at)}</span></span>
      <span class="row tight"><span class="pill ${pcTone(x)}">${esc(x.headline)}</span>${ch && x.id === ch.id ? `<span class="muted">Shown</span>` : `<button class="ghost small" type="button" data-pc-show="${x.id}">Show</button>`}</span></div>`).join("")}
      <div class="note">A newer check replaces the workbook filed on the checklist item; the earlier checks stay listed here with what they found.</div></div>` : "";
  const trail = addrOf({ view: "trail" }) || "#/admin/audit-trail";
  main.innerHTML = `<div class="pc-top"><h1>Payroll</h1>
      <p class="note">Check the month's payroll workbook before paying. Every company can use the Workbook check; ${esc(r.entity.name)} doesn't run payroll in this app.</p></div>
    <div class="pc-tabs" role="tablist" aria-label="Payroll"><button type="button" role="tab" class="pc-tab on" id="pc-tab-0" aria-selected="true" aria-controls="pc-panel" tabindex="0">${icon("verified")}Workbook check</button></div>
    <div id="pc-panel" role="tabpanel" aria-labelledby="pc-tab-0">
    <div class="card"><div class="row spread"><h2 id="pc-h2" tabindex="-1">Payroll check · ${code} · ${label}</h2>
      ${ch ? `<a class="ghost" href="/api/payroll-check/export.xlsx?entity_id=${state.entity}&month=${state.month}&check=${ch.id}">Excel report</a>` : ""}</div>
      ${upload}${head}</div>
    ${rep ? `<div class="card">${chips}${groups}${noMatch}</div>` : ""}
    ${pay}${earlier}
    <div class="note">The check reads the workbook by its headings: the Summary against each payslip, each payslip's own sums and month, and EPF, SOCSO, EIS and SKBBK against the rates. IC numbers are masked to the last 4 everywhere, the Excel report included. Each check, and each opening of an Excel report, is recorded in the <a href="${trail}">audit trail</a>.</div>
    </div>`;
  $("#pcForm").onsubmit = async ev => {
    ev.preventDefault();
    const file = $("#pcFile").files[0];
    if (!file) return toast("Choose the payroll workbook first.", true);
    const fd = new FormData(); fd.append("file", file); fd.append("entity_id", state.entity); fd.append("month", state.month);
    const go = $("#pcGo"); go.disabled = true; go.setAttribute("aria-busy", "true"); go.textContent = "Checking…";
    const here = pageHere(), idle = () => { go.disabled = false; go.removeAttribute("aria-busy"); go.textContent = ch ? "Check again" : "Check the workbook"; };
    let out;
    try { out = await api("/api/payroll-check", { form: fd }); }
    catch (e) {
      idle();
      const title = e.unsure ? `It isn't known whether ${file.name} was checked` : `${file.name} wasn't checked`;
      if (!here() || !pageWhole() || !$("#pcRefused")) return toast(`${title}. ${changeError(e)}`, true);  // another page since, or this one read again: said in a message
      $("#pcRefused").innerHTML = refusedNote(changeError(e), { title }) + (e.unsure ? "" :
        `<div class="note">${r.checks.length ? "Nothing was kept: the check below is still the latest, and its workbook stays filed." : "Nothing was kept."}</div>`);
      return;
    }
    idle();
    const picked = $("#pcFile");
    if (picked) picked.value = "";  // checked and kept: the form doesn't hold it to be sent again while the page is read
    state.pcFilter = null; toast(out.chosen?.report?.headline || "Checked");
    await afterSaved(savedPagePart(here, () => viewPayroll(main)));
  };
  // Only while this company's month is still the one asked for, and no reading of the page is under way: these stay clickable, dimmed,
  // while the next page is read (this one asked for again, too), and a draw from them then would take the place of the one being read.
  const show = (id, filter) => { if (!still() || !pageWhole()) return; if (filter) state.pcFilter = filter; viewPayroll(main, id).catch(e => toast(e.message, true)); };
  main.querySelectorAll("[data-pc-show]").forEach(b => b.onclick = () => show(+b.dataset.pcShow));
  main.querySelectorAll("[data-pc-filter]").forEach(b => b.onclick = () => show(checkId, b.dataset.pcFilter));
}
