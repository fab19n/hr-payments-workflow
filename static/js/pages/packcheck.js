"use strict";
/* ---- Check this pack (hrp/packcheck.py) ---- */
const PACK_FILE = { unchanged: ["ok", "File unchanged"], changed: ["bad", "File changed"], missing: ["bad", "File missing"],
  not_recorded: ["warn", "Not recorded in the trail"] };
// A trail entry, opened in place (toggleEntry draws it below the button).
const entryLink = (id, text) => id ? `<div><button class="ghost small" type="button" data-tx="${esc(id)}" aria-expanded="false">${esc(text)}</button><div class="tr-body" hidden></div></div>` : "";

// The drawer: whether the file is the one built, what built it, and what changed since in what it reads (grouped, each
// change with its trail entry), then what the check can't tell.
async function openPackCheck(event, file) {
  if (!(await closeDrawer())) return;
  $("#drawer").innerHTML = `<div class="ex-head"><div class="row spread"><div><div class="eyebrow">Check this pack</div><h2>${esc(file || "Audit pack")}</h2></div><button class="ghost small" id="closeDrawer">Close</button></div></div>
    <div id="pcBody"><div class="note">Loading…</div></div>`;
  showDrawer();
  return dialogDraw(dlg => packCheckFill(dlg, event, file));
}
async function packCheckFill(dlg, event, file) {
  let r;
  try {
    r = await dlg.read(api(event ? `/api/audit-pack/check?event=${encodeURIComponent(event)}`
      : `/api/audit-pack/check?entity=${state.entity}&month=${state.month}&file=${encodeURIComponent(file)}`));
  } catch (e) { dlg.check(); if ($("#pcBody")) $("#pcBody").innerHTML = `<div class="note bad-text">${esc(e.message)}</div>`; return; }
  if (!$("#pcBody")) return;
  const p = r.pack, pr = p.printed || {}, [tone, word] = PACK_FILE[r.file.state];
  const cover = pr.trail_entry ? `On its cover: ${pr.generated ? `generated ${esc(pr.generated)}, ` : ""}audit trail entry ${esc(pr.trail_entry)} · check code ${esc(pr.check_code)}${pr.worked_out ? " (worked out from the trail)" : ""}.` : "";
  const prog = p.same_program === true ? "Built by the version of the program running now." : p.same_program === false ? "Built by another version of the program." : "";
  const row = (g, x) => `<div class="tr-hist"><div><span class="mono muted">${esc(fmtWhen(x.at))}</span> · <span class="pill ${SRC_TONE[x.source] ?? "grey"}">${esc(x.source_label || "")}</span> ${esc(x.actor || "")}${x.reason ? ` · Why: ${esc(x.reason)}` : ""}${x.late ? ` <span class="pill warn">Sealed late</span>` : ""}</div>
    ${g.key === "packs" ? `<div class="tr-change"><b>Built ${esc(x.record)}</b></div>` : changeHtml(x)}
    ${entryLink(x.entry, `Entry ${x.entry}${x.headline ? `: ${x.headline}` : ""}`)}</div>`;
  const groups = r.changes.groups.map(g => `<h3>${esc(g.label)} · ${esc(g.count)}</h3>${g.rows.map(x => row(g, x)).join("")}
    ${g.more ? `<div class="note">And ${esc(g.more)} more, not listed here.</div>` : ""}`).join("");
  const docs = r.documents.problems.length
    ? `<h3>Its documents' files now · ${esc(r.documents.problems.length)}</h3>${r.documents.problems.map(d => `<div class="note"><b>${esc(d.name)}</b> on ${esc(d.owner)}: ${esc(d.why)}</div>`).join("")}`
    : r.documents.checked ? `<div class="note">The ${esc(r.documents.checked)} document file${r.documents.checked === 1 ? "" : "s"} it would hold now still match${r.documents.checked === 1 ? "es" : ""} the fingerprint taken at upload.</div>` : "";
  $("#pcBody").innerHTML = `<div class="row"><span class="pill ${tone}">${esc(word)}</span></div>
    <div class="note">${esc(r.file.text)}</div>
    <div class="note">${esc(r.company)} · ${esc(r.label)}. ${r.recorded ? `Built ${esc(fmtWhen(p.at))}${p.actor ? ` by ${esc(p.actor)}` : ""}${p.via ? ` for the ${esc(p.via)}` : ""}.` : `File saved ${esc(fmtWhen(p.at))}.`} ${cover} ${prog}</div>
    ${entryLink(p.entry, `Entry ${p.entry}: the pack built`)}
    <h2>Since it was built</h2><div class="note">${esc(r.changes.summary)}</div>${groups}${docs}
    <h2>What this check can't tell</h2>${r.cannot_tell.map(t => `<div class="note">${esc(t)}</div>`).join("")}`;
}

// Marks the month on show as filed. With anything still open (Before you print, or the pack not built or out of date)
// it asks first, naming it: a month filed outside the app can still be marked. afterBuild: asked from 'Printed and
// filed?' on the Audit page.
async function markFiled(afterBuild) {
  // The company and month the button was on. Another page opened while they are looked at: nothing is asked over it and nothing is filed.
  const entity = state.entity, month = state.month, here = pageHere();
  const r = await api(`/api/audit-readiness?entity_id=${entity}&month=${month}`);
  if (!here()) return;
  if (r.still_open.length && !(await ask(`${r.entity.code} still has things open:${afterBuild ? "" : "\nIf this month was already filed outside the app, that is fine."}`, { title: `Mark ${r.label} as filed?`, yes: "File anyway", no: "Go back", tone: "brand", glyph: "pack", list: r.still_open.map(text => ({ glyph: "alert", tone: "warn", text })), closing: "A filed month can be reopened later." }))) return;
  await api("/api/months/close", { json: { entity_id: entity, month, closed: true } });
  toast(`${r.label} marked as filed`); await afterSaved(render);
  // The password is typed each time, so a backup is offered, not made.
  if (await ask("A backup keeps the filed month safe if this PC fails. You'll be asked for the backup password next.", { title: `${r.label} is filed. Make an encrypted backup now?`, yes: "Make a backup", no: "Not now", safe: "yes", tone: "brand", glyph: "vault", closing: "Not now changes nothing; back up any time from Backup." })) await goToBackupPassword();
}

// A line of Before you print opens the screen that fixes it, for this company and month: the payment's drawer on the Payments
// register, the item on the Monthly checklist, the Bank statements page on that account, or the SQL page.
function fixIt(where, id) {
  const view = { payment: "entity", task: "checklist", account: "bank", sql: "sql" }[where];
  return goTo({ view, payment_id: where === "payment" ? id : null, task_id: where === "task" ? id : null, account_id: where === "account" ? id : null });
}

