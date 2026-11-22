"use strict";
/* ---- Monthly checklist ---- */
const chkDocName = k => setupDocName(state.setup.chk, k);
const chkCompletion = k => (state.setup.chk?.completions || []).find(c => c.key === k)?.label || k;

async function setupChecklist(box) {
  const S = state.setup, e = ent();
  if (!e) { box.innerHTML = `${setupHead("checklist", setupSpec())}${emptyState({ glyph: "company", title: "Add a company first.", body: "Each company has its own monthly checklist. Once one is added, its checklist is set up here.", action: { label: "Go to Companies", attr: "data-setup-kind", value: "entities", glyph: "company" } })}`; return; }
  const d = await api(`/api/setup/checklist?entity=${state.entity}`);
  if (!(box = setupBox(box))) return;
  S.chk = d;
  const code = d.code || e.code, items = d.items || [];
  // A company added in Setup starts with the starter checklist: while it is untouched and no month is set up, a copy may replace it.
  const copy = (d.replaceable || !items.some(it => it.in_use || termOn(it))) && (d.others || []).length;
  const row = it => {
    const t = it.now || {}, rule = asRule(t.rule);
    return `<tr${termOn(it, d.default_from) ? "" : ` class="muted"`}><td><button class="link" data-chk-open="${it.id}">${esc(t.title || it.code)}</button></td>
      <td>${esc(dueText(t))}${+t.deadline && !NO_DEADLINE.includes(it.completion) ? `<div class="note">Deadline${t.submit_as ? ` · submitted as ${esc(t.submit_as)}` : ""}</div>` : ""}</td>
      <td>${esc(chkCompletion(it.completion))}${it.completion === "payments" && rule?.name?.[1] ? `<div class="note">${esc(rule.name[1])}</div>` : ""}</td>
      <td>${docChips(asList(t.docs), chkDocName)}</td><td>${termPills(it, d.default_from)}</td></tr>`;
  };
  box.innerHTML = `${setupHead("checklist", setupSpec(), { title: `Monthly checklist · ${code}`, intro: `What each month's checklist holds for ${code}, in order. Click an item to change it. A change starts from a payroll month you choose: the months before it keep the checklist they had, and filed months never change.`,
      actions: `${copy ? `<button class="ghost" data-chk-copy="1">Copy from another company</button>` : ""}<button class="btn" data-chk-new="1">${icon("plus")}Add item</button>` })}
    <div class="card">
      <div class="row">${deletedToggle("checklist")}</div>
      <div class="tbl-wrap"><table><thead><tr><th>Item</th><th>Due</th><th>Done when</th><th>Documents</th><th>Status</th></tr></thead><tbody>
        ${items.map(row).join("") || `<tr><td colspan="5" class="empty">${esc(code)} has no monthly checklist yet. Add an item${copy ? ", or copy another company's checklist" : ""}.</td></tr>`}
      </tbody></table></div><div id="setupDeleted"></div></div>`;
  await drawDeleted("checklist");
}

// The payments rule of an item done by its payments: which payments it covers and what each needs.
function ruleHtml(rule) {
  const d = state.setup.chk, cats = asList(rule.categories), rd = asList(rule.docs), ro = asList(rule.on_item), names = asList(rule.name);
  const types = pickTypes(d.payment_types, cats), docs = pickTypes((d.doc_types || []), [...rd, ...ro]);
  const dir = rule.direction || "";
  return `<fieldset class="chk-rule" id="cl-rule"><legend>Which payments, and what each needs</legend>
    <div role="group" aria-label="Payment types covered" class="req-docs"><span class="muted">Payment types covered (none ticked: any type)</span>
      ${types.map(x => tickBox("cl-rt-" + x.key, x, cats.includes(x.key))).join("") || `<div class="note">No payment types in use.</div>`}</div>
    <label class="field"><span>Money</span><select id="cl-rdir"><option value="">Either</option><option value="out" ${dir === "out" ? "selected" : ""}>Money out</option><option value="in" ${dir === "in" ? "selected" : ""}>Money in</option></select></label>
    <label class="field"><span>Words in the description or payee</span><input id="cl-rwords" value="${esc(asList(rule.words).join(", "))}" spellcheck="false" autocomplete="off" placeholder="KWSP, KUMPULAN WANG">
      <span class="note">Whole words, with commas between them. Empty: any payment of the types above.</span></label>
    <div role="group" aria-label="Documents each payment needs" class="req-docs"><span class="muted">Each payment needs (at least one)</span>
      ${docs.map(x => tickBox("cl-rd-" + x.key, x, rd.includes(x.key))).join("") || `<div class="note">No document types in use.</div>`}</div>
    <div role="group" aria-label="Documents that may be filed on the item instead" class="req-docs"><span class="muted">Of these, may be filed on this item instead</span>
      ${docs.map(x => tickBox("cl-ro-" + x.key, x, ro.includes(x.key), ` data-ro="${esc(x.key)}"`)).join("")}<div class="note" id="cl-ro-none">Tick a document each payment needs first.</div></div>
    <label class="row tight" style="grid-column:1/-1"><input type="checkbox" id="cl-rpaid" ${rule.paid ? "checked" : ""}><span>A paid payment counts without its documents</span></label>
    <label class="field" style="grid-column:1/-1"><span>With no such payment in the month, it is done once the statements are in, saying</span><input id="cl-rnone" maxlength="200" value="${esc(rule.none || "")}" placeholder="no overseas claims this month">
      <span class="note">Leave it empty when the month always has such a payment.</span></label>
    <label class="field"><span>What one is called</span><input id="cl-rname1" maxlength="80" value="${esc(names[0] || "")}" placeholder="KWSP payment"></label>
    <label class="field"><span>What several are called</span><input id="cl-rname2" maxlength="80" value="${esc(names[1] || "")}" placeholder="KWSP payments"></label>
  </fieldset>`;
}

// The drawer of one checklist item (id "new" to add one). keep: what was typed and not saved, when it is drawn again
// after a stop or use again; saved: what the last save did.
async function openChecklist(id, { force = false, keep = {}, saved = null } = {}) {
  if (!force && !(await mayLeave())) return;
  const S = state.setup, d = S.chk;
  if (!d) return;
  const isNew = id === "new", it = isNew ? null : (d.items || []).find(x => x.id === +id);
  if (!isNew && !it) return closeDrawer(true);
  // The month shown: the one typed before it was drawn again, else the earliest not filed; the term in force then.
  const m0 = /^\d{4}-\d{2}$/.test(keep["cl-from"] || "") ? keep["cl-from"] : d.default_from || "";
  const t = (it && termAt(it, m0)) || { title: "", detail: "", due_offset: 0, due_day: "", docs: [], deadline: 0, submit_as: null, rule: null };
  // Built-in completions have a code of their own: a company has each at most once. SQL's books only for a company kept in SQL.
  const offered = (d.completions || []).filter(c => (!c.code || !(d.items || []).some(x => x.code === c.code))
    && (c.key !== "books" || d.uses_sql !== false));
  const completion = isNew ? offered[0]?.key || "hand" : it.completion, on = isNew || termOn(it, m0);
  const used = +it?.used || 0, code = d.code || ent()?.code || "";
  state.openPayment = null; state.why = null; S.drawer = null; S.remOpen = null; S.chkOpen = { id: isNew ? "new" : it.id, completion, term: isNew ? null : t, on };
  $("#drawer").innerHTML = `
    <div class="ex-head"><div class="row spread"><div><div class="eyebrow">Monthly checklist · ${esc(code)}</div><h2>${isNew ? "Add item" : esc(t.title || it.code)}</h2></div><button class="ghost small" id="closeDrawer">Close</button></div>
      ${isNew ? "" : termPills(it, d.default_from)}</div>
    ${saved ? effectCard(saved, saved.head || "Saved", "checklist item") : ""}
    <form class="form setup-form" id="chkForm">
      ${isNew ? `<label class="field" style="grid-column:1/-1"><span>Done when</span><select id="cl-completion">${offered.map(c => `<option value="${esc(c.key)}">${esc(c.label)}</option>`).join("")}</select>
          <span class="note">Fixed once the item is added. A company has each of the built-in ones once at most.</span></label>`
        : `<label class="field locked" style="grid-column:1/-1"><span>Done when</span><input value="${esc(chkCompletion(completion))}" readonly tabindex="-1"><span class="note">Fixed once the item is added.</span></label>`}
      <label class="field" style="grid-column:1/-1"><span>Title</span><input id="cl-title" maxlength="200" value="${esc(t.title || "")}" required></label>
      <label class="field" style="grid-column:1/-1"><span>Detail</span><textarea id="cl-detail" rows="3" maxlength="2000">${esc(t.detail || "")}</textarea></label>
      <label class="field"><span>Due in</span><select id="cl-off"><option value="0">The payroll month</option><option value="1" ${+t.due_offset ? "selected" : ""}>The month after</option></select></label>
      <label class="field"><span>Day of the month</span><input id="cl-day" type="number" min="1" max="31" step="1" value="${esc(t.due_day ?? "")}" required><span class="note">A shorter month uses its last day.</span></label>
      <div role="group" aria-label="Documents for this item" class="req-docs" id="cl-docs">${chkDocsHtml(asList(t.docs))}</div>
      <label class="row tight" id="cl-deadline-f" style="grid-column:1/-1"><input type="checkbox" id="cl-deadline" ${+t.deadline ? "checked" : ""}><span>A deadline: Next up shows it from a few days before</span></label>
      <label class="field" id="cl-submit-f" style="grid-column:1/-1"><span>Submitted as (optional)</span><input id="cl-submit" maxlength="30" value="${esc(t.submit_as || "")}" placeholder="KWSP">
        <span class="note">Items due the same day with a name here are one Next up row, e.g. Submit Oct KWSP, PERKESO and e-PCB.</span></label>
      ${isNew || completion === "payments" ? ruleHtml(asRule(t.rule) || {}) : ""}
      <label class="field"><span>From which month?</span><input id="cl-from" type="month" value="${esc(m0)}"${d.first_allowed ? ` min="${esc(d.first_allowed)}"` : ""} required>
        <span class="note">Months before this keep the checklist they had. Filed months never change.${isNew ? "" : " The item shows as it is in this month."}</span><span class="note" id="cl-from-note" hidden></span></label>
      <label class="field"><span>Why are you making this change? (optional)</span><input id="cl-reason" maxlength="500" autocomplete="off"></label>
      <div class="row" style="grid-column:1/-1"><button class="ghost" type="button" data-chk-preview="1">Preview</button><button class="btn" type="submit">${isNew ? "Add item" : "Save"}</button></div></form>
    <div id="cl-preview" data-preview-out></div>
    ${isNew ? "" : `<div><h3>Where used</h3><div class="note">${used ? `In ${plural(used, "month")} so far.` : "Not in any month yet."}</div></div>
    <div class="row" id="cl-act-row">${chkActRow(it, on)}</div>
    <div class="note" id="cl-act-note">${chkActNote(it, on)}</div>
    ${whyForm()}
    ${termsHtml(it, h => `${h.title}, due the ${dueText(h)}${asList(h.docs).length ? `, ${asList(h.docs).map(chkDocName).join(", ")}` : ""}`)}
    ${histSection("checklist_items", it.id)}`}`;
  showDrawer();
  if (!isNew) S.chkOpen.filled = termInputs("cl-");  // as filled in, before what was typed is put back
  watchDrawer(keep);
  setupPaint();  // after keep, as what it put back may show or hide parts
}
// The item's documents picker: those in use, plus any chosen that were stopped since.
const chkDocsHtml = docs => `<span class="muted">Documents for this item</span>
  ${pickTypes(state.setup.chk?.doc_types, docs).map(x => tickBox("cl-doc-" + x.key, x, docs.includes(x.key))).join("") || `<div class="note">No document types in use.</div>`}`;
// Stop using when the item is in use in the month chosen, else Use again; Delete while never used.
const chkActRow = (it, on) => `${on ? `<button class="ghost" type="button" data-chk-act="stop">Stop using</button>` : `<button class="ghost" type="button" data-chk-act="use">Use again</button>`}
  ${it.can_delete ? `<button class="btn danger small" type="button" data-chk-act="delete">Delete</button>` : ""}`;
const chkActNote = (it, on) => `${on ? "Stopping it leaves it out of the months from the month above on, changes planned for later months included; where something is filed on it or it is ticked, it stays." : "Use again puts it back from the month above, with the wording it had."}
  ${it.can_delete ? "" : +it.system ? " The app relies on it, so it can't be deleted." : " It can't be deleted once it has been used; stop using it instead."}`;
// The term in force in another month, put in the drawer's inputs.
function chkFill(t) {
  $("#cl-title").value = t.title || ""; $("#cl-detail").value = t.detail || "";
  $("#cl-off").value = +t.due_offset ? "1" : "0"; $("#cl-day").value = t.due_day ?? "";
  $("#cl-docs").innerHTML = chkDocsHtml(asList(t.docs));
  $("#cl-deadline").checked = !!+t.deadline; $("#cl-submit").value = t.submit_as || "";
  if ($("#cl-rule")) $("#cl-rule").outerHTML = ruleHtml(asRule(t.rule) || {});
}
function chkMonth() {
  const S = state.setup, O = S.chkOpen;
  if (!O || O.id === "new" || O.id === "copy") return;
  termMonth("cl-", O, (S.chk?.items || []).find(x => x.id === O.id), chkFill, (it, on) => {
    $("#cl-act-row").innerHTML = chkActRow(it, on); $("#cl-act-note").innerHTML = chkActNote(it, on);
  });
}

// The item's fields as typed: all of them (a change sends the whole term); the completion only when adding.
function chkFields(isNew) {
  // The term the inputs were filled in from: its documents and rule keep their order.
  const S = state.setup, d = S.chk, O = S.chkOpen, it = (d.items || []).find(x => x.id === O.id), t = O.term || it?.now || {};
  const comp = $("#cl-completion")?.value ?? O.completion, rule0 = asRule(t.rule) || {}, had = asList(t.docs);
  const day = $("#cl-day").value.trim(), deadline = $("#cl-deadline").checked && !NO_DEADLINE.includes(comp) ? 1 : 0;
  const f = { title: $("#cl-title").value.trim(), detail: $("#cl-detail").value.trim(), due_offset: +$("#cl-off").value, due_day: day === "" ? null : +day,
    docs: ticked("cl-doc-", pickTypes(d.doc_types, had), had), deadline, submit_as: deadline ? $("#cl-submit").value.trim() || null : null, rule: null };
  if (comp === "payments") {
    const rd = asList(rule0.docs), ro = asList(rule0.on_item), list = pickTypes(d.doc_types, [...rd, ...ro]), docs = ticked("cl-rd-", list, rd);
    f.rule = { categories: ticked("cl-rt-", pickTypes(d.payment_types, asList(rule0.categories)), asList(rule0.categories)),
      direction: $("#cl-rdir").value || null, words: splitWords($("#cl-rwords").value), docs,
      on_item: ticked("cl-ro-", list, ro).filter(k => docs.includes(k)), paid: $("#cl-rpaid").checked,
      none: $("#cl-rnone").value.trim() || null, name: [$("#cl-rname1").value.trim(), $("#cl-rname2").value.trim()] };
  }
  if (isNew) f.completion = comp;
  return f;
}

// After a checklist change: the page's copy of the codes is read again, the list drawn again, and the item's drawer
// opened again on what the change did.
async function chkDone(r, id, head, keep = {}, dialogSaved = false) {
  toast(`${head}. ${effectText(r.affected, "checklist item")}`);
  return afterSaved(async o => { await reloadMeta(); return render(o); }, () => {
    if (id != null && (state.setup.chk?.items || []).some(x => x.id === +id)) return openChecklist(+id, { force: true, keep, saved: { ...r, head } });
    closeDrawer(true);
  }, { dialogSaved });
}

// Preview (nothing kept) or Save: adds the item, or changes it from the month chosen.
async function chkSave(preview) {
  const S = state.setup, d = S.chk, O = S.chkOpen;
  if (!d || !O || O.id === "copy") return;
  const isNew = O.id === "new";
  const body = { action: isNew ? "add" : "change", entity_id: d.entity_id ?? state.entity, from_month: fromMonth("#cl-from"), fields: chkFields(isNew), preview: !!preview };
  if (!isNew) body.item_id = O.id;
  const reason = $("#cl-reason").value.trim();
  if (reason) body.reason = reason;
  const r = await api("/api/setup/checklist", { json: body });
  if (preview) return showPreview("#cl-preview", r, "checklist item");
  // Drawn again on the month the change starts from, so it shows the term just saved.
  return chkDone(r, isNew ? r.item_id : O.id, isNew ? "Item added" : "Saved", { "cl-from": body.from_month }, true);
}

// Stop using, Use again (from the month chosen) and Delete ask why first.
async function chkAct(act, btn) {
  const S = state.setup, d = S.chk, O = S.chkOpen;
  if (!d || !O || O.id === "new" || O.id === "copy") return;
  const label = { stop: "Stop using it", use: "Use it again", delete: "Delete it" }[act];
  if (!label) return;
  if (act !== "delete") fromMonth("#cl-from");
  return askWhy(btn, label, async reason => {
    const body = { action: act, entity_id: d.entity_id ?? state.entity, item_id: O.id, reason };
    if (act !== "delete") body.from_month = fromMonth("#cl-from");
    const r = await api("/api/setup/checklist", { json: body });
    if (act === "delete") { closeDrawer(true); toast("Item deleted"); return afterSaved(async o => { await reloadMeta(); return render(o); }); }
    const keep = { ...drawerEdits(), "cl-from": body.from_month };
    return chkDone(r, O.id, act === "stop" ? "Stopped" : "In use again", keep);
  });
}

// Copy another company's checklist, for a company with no item in use.
async function openChkCopy({ force = false } = {}) {
  if (!force && !(await mayLeave())) return;
  const S = state.setup, d = S.chk, others = d?.others || [];
  if (!others.length) return;
  const code = d.code || ent()?.code || "";
  state.openPayment = null; state.why = null; S.drawer = null; S.remOpen = null; S.chkOpen = { id: "copy" };
  $("#drawer").innerHTML = `
    <div class="ex-head"><div class="row spread"><div><div class="eyebrow">Monthly checklist · ${esc(code)}</div><h2>Copy from another company</h2></div><button class="ghost small" id="closeDrawer">Close</button></div></div>
    <form class="form setup-form" id="chkCopyForm">
      <label class="field" style="grid-column:1/-1"><span>Copy the checklist of</span><select id="cp-from">${others.map(o => `<option value="${o.id}">${esc(o.code)} · ${esc(o.name)} (${plural(+o.items || 0, "item")})</option>`).join("")}</select>
        <span class="note">Its items in force in the month below are added to ${esc(code)}, with their wording, due dates and documents.${d.replaceable ? ` They replace the starter checklist ${esc(code)} was given.` : ""} You can change them here afterwards.</span></label>
      <label class="field"><span>From which month?</span><input id="cl-from" type="month" value="${esc(d.default_from || "")}"${d.first_allowed ? ` min="${esc(d.first_allowed)}"` : ""} required>
        <span class="note">Months before this keep the checklist they had. Filed months never change.</span></label>
      <label class="field"><span>Why are you making this change? (optional)</span><input id="cl-reason" maxlength="500" autocomplete="off"></label>
      <div class="row" style="grid-column:1/-1"><button class="ghost" type="button" data-chk-copy-preview="1">Preview</button><button class="btn" type="submit">Copy</button></div></form>
    <div id="cl-preview" data-preview-out></div>`;
  showDrawer();
  watchDrawer();
}
async function chkCopySave(preview) {
  const d = state.setup.chk;
  if (!d || state.setup.chkOpen?.id !== "copy") return;
  const body = { action: "copy", entity_id: d.entity_id ?? state.entity, from_month: fromMonth("#cl-from"), copy_from: +$("#cp-from").value, preview: !!preview };
  const reason = $("#cl-reason").value.trim();
  if (reason) body.reason = reason;
  const r = await api("/api/setup/checklist", { json: body });
  if (preview) return showPreview("#cl-preview", r, "checklist item");
  toast(`Checklist copied. ${effectText(r.affected, "checklist item")}`);
  closeDrawer(true);
  return afterSaved(async o => { await reloadMeta(); return render(o); });
}

