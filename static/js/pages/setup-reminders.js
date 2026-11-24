"use strict";
/* ---- Joiner and leaver reminders ---- */
const remDocName = k => setupDocName(state.setup.rem, k);
const REM_HINT = "{name} in the title becomes the person's short name; {date} in the detail becomes the start date or last day. No other braces can be used. The wording doesn't change by itself when you change the days or the salary.";

async function setupReminders(box) {
  const d = await api("/api/setup/reminders");
  if (!(box = setupBox(box))) return;
  state.setup.rem = d;
  const rules = d.rules || [];
  const row = r => {
    const t = r.now || {};
    return `<tr${termOn(r, d.default_from) ? "" : ` class="muted"`}><td><button class="link" data-rem-open="${r.id}">${esc(t.title || r.key)}</button>${r.short_name ? `<div class="note">${esc(r.short_name)}</div>` : ""}</td>
      <td>${r.kind === "leaver" ? "Leaver" : "Joiner"}</td><td>${esc(remDays(t.days, r.kind))}</td><td>${esc(remSalary(t.salary_over))}</td>
      <td>${docChips(asList(t.docs), remDocName)}</td><td>${termPills(r, d.default_from)}</td></tr>`;
  };
  box.innerHTML = `${setupHead("reminders", setupSpec(), { intro: "A recurring salary's start date or last day adds these reminders to the checklist, each in the month it falls due, for every company. Click one to change it. A change applies to people starting (or leaving) from a month you choose, and filed months never change.",
      actions: `<button class="btn" data-rem-new="1">${icon("plus")}Add reminder</button>` })}
    <div class="card">
    <div class="row">${deletedToggle("reminders")}</div>
    <div class="tbl-wrap"><table><thead><tr><th>Reminder</th><th>For</th><th>When</th><th>Salary</th><th>Documents</th><th>Status</th></tr></thead><tbody>
      ${rules.map(row).join("") || `<tr><td colspan="6" class="empty">None yet.</td></tr>`}
    </tbody></table></div><div id="setupDeleted"></div></div>`;
  await drawDeleted("reminders");
}

// The drawer of one reminder (id "new" to add one); keep and saved as for a checklist item.
async function openReminder(id, { force = false, keep = {}, saved = null } = {}) {
  if (!force && !(await mayLeave())) return;
  const S = state.setup, d = S.rem;
  if (!d) return;
  const isNew = id === "new", r = isNew ? null : (d.rules || []).find(x => x.id === +id);
  if (!isNew && !r) return closeDrawer(true);
  // The month shown: the one typed before it was drawn again, else the earliest not filed; the term in force then.
  const m0 = /^\d{4}-\d{2}$/.test(keep["rm-from"] || "") ? keep["rm-from"] : d.default_from || "";
  const t = (r && termAt(r, m0)) || { days: "", salary_over: null, title: "", detail: "", docs: [] };
  const kind = isNew ? "joiner" : r.kind, on = isNew || termOn(r, m0), used = +r?.used || 0, days = +t.days || 0;
  state.openPayment = null; state.why = null; S.drawer = null; S.chkOpen = null; S.remOpen = { id: isNew ? "new" : r.id, kind, term: isNew ? null : t, on };
  $("#drawer").innerHTML = `
    <div class="ex-head"><div class="row spread"><div><div class="eyebrow">Joiner and leaver reminder</div><h2>${isNew ? "Add reminder" : esc(t.title || r.key)}</h2></div><button class="ghost small" id="closeDrawer">Close</button></div>
      ${isNew ? "" : termPills(r, d.default_from)}</div>
    ${saved ? effectCard(saved, saved.head || "Saved", "reminder") : ""}
    <form class="form setup-form" id="remForm">
      ${isNew ? `<label class="field"><span>Key</span><input id="rm-key" class="mono" maxlength="20" spellcheck="false" autocomplete="off" required placeholder="ecp22">
          <span class="note">Lower-case letters, digits and _, 2 to 20, starting with a letter. Fixed once added.</span></label>
        <label class="field"><span>For</span><select id="rm-kind"><option value="joiner">A joiner (from the start date)</option><option value="leaver">A leaver (from the last day)</option></select>
          <span class="note">Fixed once added.</span></label>`
        : `<label class="field locked"><span>Key</span><input class="mono" value="${esc(r.key)}" readonly tabindex="-1"><span class="note">Fixed once added.</span></label>
        <label class="field locked"><span>For</span><input value="${kind === "leaver" ? "A leaver (from the last day)" : "A joiner (from the start date)"}" readonly tabindex="-1"><span class="note">Fixed once added.</span></label>`}
      <label class="field" style="grid-column:1/-1"><span>Short name</span><input id="rm-short" maxlength="40" value="${esc(r?.short_name || "")}" placeholder="e-CP22">
        <span class="note">Next up names reminders due together by their short names, and the recurring payment drawer lists them.</span></label>
      <label class="field"><span>Number of days</span><input id="rm-days" type="number" min="0" max="366" step="1" value="${t.days === "" || t.days == null ? "" : Math.abs(days)}" required>
        <span class="note">0 is on the day itself.</span></label>
      <label class="field"><span>Before or after <span id="rm-what">${kind === "leaver" ? "the last day" : "the start date"}</span></span><select id="rm-when"><option value="after">After</option><option value="before" ${days < 0 ? "selected" : ""}>Before</option></select></label>
      <label class="field" style="grid-column:1/-1"><span>Only when the monthly salary is over (optional)</span><input id="rm-salary" type="number" step="0.01" min="0" value="${esc(t.salary_over ?? "")}">
        <span class="note">Leave it empty for any salary.</span></label>
      <label class="field" style="grid-column:1/-1"><span>Title</span><input id="rm-title" maxlength="200" value="${esc(t.title || "")}" required placeholder="Submit e-CP22 for {name}"></label>
      <label class="field" style="grid-column:1/-1"><span>Detail</span><textarea id="rm-detail" rows="3" maxlength="2000" required>${esc(t.detail || "")}</textarea>
        <span class="note">${esc(REM_HINT)}</span></label>
      <div role="group" aria-label="Documents for this reminder" class="req-docs" id="rm-docs">${remDocsHtml(asList(t.docs))}</div>
      <label class="field" style="grid-column:1/-1"><span>For people starting (or leaving) from which month?</span><input id="rm-from" type="month" value="${esc(m0)}"${d.first_allowed ? ` min="${esc(d.first_allowed)}"` : ""} required>
        <span class="note">The month of the start date or last day. People starting or leaving before it keep the reminders they had. Filed months never change.${isNew ? "" : " The reminder shows as it is for this month."}</span><span class="note" id="rm-from-note" hidden></span></label>
      <label class="field" style="grid-column:1/-1"><span>Why are you making this change? (optional)</span><input id="rm-reason" maxlength="500" autocomplete="off"></label>
      <div class="row" style="grid-column:1/-1"><button class="ghost" type="button" data-rem-preview="1">Preview</button><button class="btn" type="submit">${isNew ? "Add reminder" : "Save"}</button></div></form>
    <div id="rm-preview" data-preview-out></div>
    ${isNew ? "" : `<div><h3>Where used</h3><div class="note">${used ? `${plural(used, "reminder")} made so far.` : "No reminder made yet."}</div></div>
    <div class="row" id="rm-act-row">${remActRow(r, on)}</div>
    <div class="note" id="rm-act-note">${remActNote(r, on)}</div>
    ${whyForm()}
    ${termsHtml(r, h => `${h.title}, ${lowerFirst(remDays(h.days, kind))}${h.salary_over == null || h.salary_over === "" ? "" : `, ${lowerFirst(remSalary(h.salary_over))}`}`)}
    ${histSection("people_tasks", r.id)}`}`;
  showDrawer();
  if (!isNew) S.remOpen.filled = termInputs("rm-");  // as filled in, before what was typed is put back
  watchDrawer(keep);
  setupPaint();
}
const remDocsHtml = docs => `<span class="muted">Documents for this reminder</span>
  ${pickTypes(state.setup.rem?.doc_types, docs).map(x => tickBox("rm-doc-" + x.key, x, docs.includes(x.key))).join("") || `<div class="note">No document types in use.</div>`}`;
// Stop using when the reminder is in use for the month chosen, else Use again; Delete while never used.
const remActRow = (r, on) => `${on ? `<button class="ghost" type="button" data-rem-act="stop">Stop using</button>` : `<button class="ghost" type="button" data-rem-act="use">Use again</button>`}
  ${r.can_delete ? `<button class="btn danger small" type="button" data-rem-act="delete">Delete</button>` : ""}`;
const remActNote = (r, on) => `${on ? "Stopping it leaves it out for people starting (or leaving) from the month above on, changes planned for later months included; one ticked or with something filed on it stays." : "Use again puts it back for people starting (or leaving) from the month above, with the wording it had."}
  ${r.can_delete ? "" : +r.system ? " The app relies on it, so it can't be deleted." : " It can't be deleted once it has been used; stop using it instead."}`;
// The term in force for another month, put in the drawer's inputs.
function remFill(t) {
  const days = +t.days || 0;
  $("#rm-days").value = t.days === "" || t.days == null ? "" : Math.abs(days); $("#rm-when").value = days < 0 ? "before" : "after";
  $("#rm-salary").value = t.salary_over ?? ""; $("#rm-title").value = t.title || ""; $("#rm-detail").value = t.detail || "";
  $("#rm-docs").innerHTML = remDocsHtml(asList(t.docs));
}
function remMonth() {
  const S = state.setup, O = S.remOpen;
  if (!O || O.id === "new") return;
  termMonth("rm-", O, (S.rem?.rules || []).find(x => x.id === O.id), remFill, (r, on) => {
    $("#rm-act-row").innerHTML = remActRow(r, on); $("#rm-act-note").innerHTML = remActNote(r, on);
  });
}

function remFields() {
  // The term the inputs were filled in from: its documents keep their order.
  const S = state.setup, d = S.rem, O = S.remOpen, r = (d.rules || []).find(x => x.id === O.id), had = asList((O.term || r?.now)?.docs);
  const n = $("#rm-days").value.trim(), sal = $("#rm-salary").value.trim();
  return { days: n === "" ? null : Math.abs(+n) * ($("#rm-when").value === "before" ? -1 : 1), salary_over: sal === "" ? null : +sal,
    title: $("#rm-title").value.trim(), detail: $("#rm-detail").value.trim(), docs: ticked("rm-doc-", pickTypes(d.doc_types, had), had) };
}

async function remDone(r, id, head, keep = {}, dialogSaved = false) {
  toast(`${head}. ${effectText(r.affected, "reminder")}`);
  return afterSaved(async o => { await reloadMeta(); return render(o); }, () => {
    if (id != null && (state.setup.rem?.rules || []).some(x => x.id === +id)) return openReminder(+id, { force: true, keep, saved: { ...r, head } });
    closeDrawer(true);
  }, { dialogSaved });
}

// Preview (nothing kept) or Save: adds the reminder, or changes it for people starting (or leaving) from the month chosen.
async function remSave(preview) {
  const S = state.setup, d = S.rem, O = S.remOpen;
  if (!d || !O) return;
  const isNew = O.id === "new";
  const body = { action: isNew ? "add" : "change", short_name: $("#rm-short").value.trim() || null, from_month: fromMonth("#rm-from"), fields: remFields(), preview: !!preview };
  if (isNew) {
    body.key = $("#rm-key").value.trim().toLowerCase(); body.kind = $("#rm-kind").value;
    if (!/^[a-z][a-z0-9_]{1,19}$/.test(body.key)) throw new Error("The key needs 2 to 20 lower-case letters, digits or _, starting with a letter.");
  } else body.id = O.id;
  const reason = $("#rm-reason").value.trim();
  if (reason) body.reason = reason;
  const r = await api("/api/setup/reminders", { json: body });
  if (preview) return showPreview("#rm-preview", r, "reminder");
  // Drawn again on the month the change starts from, so it shows the term just saved.
  const keep = { "rm-from": body.from_month };
  if (!isNew) return remDone(r, O.id, "Saved", keep, true);
  // A new reminder is found by the id the server gives, else by its key.
  const nid = r.id ?? r.item_id;
  await remDone(r, nid, "Reminder added", keep, true);
  if (nid == null) { const x = (state.setup.rem?.rules || []).find(y => y.key === body.key); if (x) openReminder(x.id, { force: true, keep, saved: { ...r, head: "Reminder added" } }); }
}

async function remAct(act, btn) {
  const S = state.setup, O = S.remOpen;
  if (!S.rem || !O || O.id === "new") return;
  const label = { stop: "Stop using it", use: "Use it again", delete: "Delete it" }[act];
  if (!label) return;
  if (act !== "delete") fromMonth("#rm-from");
  return askWhy(btn, label, async reason => {
    const body = { action: act, id: O.id, reason };
    if (act !== "delete") body.from_month = fromMonth("#rm-from");
    const r = await api("/api/setup/reminders", { json: body });
    if (act === "delete") { closeDrawer(true); toast("Reminder deleted"); return afterSaved(async o => { await reloadMeta(); return render(o); }); }
    const keep = { ...drawerEdits(), "rm-from": body.from_month };
    return remDone(r, O.id, act === "stop" ? "Stopped" : "In use again", keep);
  });
}

// The reminders a salary's start date and last day add, by their short names, for the recurring payment drawer.
function reminderNote() {
  if (!Array.isArray(state.meta.people_tasks)) return "A salary's start date and last day also add reminders to the checklist, each in the month it falls due (Setup › Joiner and leaver reminders).";
  const live = state.meta.people_tasks.filter(isActive);
  const name = t => String(t.short_name || t.title || t.key || "").replace(/\{name\}/g, "the person").replace(/\{date\}/g, "the date").trim();
  const of = kind => live.filter(t => t.kind === kind).map(name).filter(Boolean);
  const parts = [of("joiner").length ? `${andList(of("joiner"))} for a joiner` : "", of("leaver").length ? `${andList(of("leaver"))} for a leaver` : ""].filter(Boolean);
  return parts.length ? `A salary's start date and last day also add reminders to the checklist, each in the month it falls due: ${parts.join(", ")}. One due in a month not set up yet shows in the latest month set up until then, without counting there.`
    : "No joiner or leaver reminders are in use, so a start date or last day adds none to the checklist.";
}

// The line above the app's name: the organisation's name from General settings, as saved (empty: no line).
function paintOrg() {
  const el = $("#orgName");
  if (!el || !state.meta?.settings) return;
  const n = String(state.meta.settings.organisation_name || "").trim();
  el.textContent = n; el.hidden = !n;
}

