"use strict";
/* ---------------- Setup › Required documents (slice 9c) ----------------
   The grid of design/canvas/SetupRequired.dc.html: payment types down the side, document types across, for every company or one, as they are
   in one payroll month. A box clicked is kept on this page, marked Changed, not saved yet; Save sends every changed type in one request (one
   change of the audit trail with its one reason, all or nothing: hrp/masters.py required_save_many) with what the page showed for each, so the
   server refuses it when the records have moved since. A save from a month replaces the type's later sets, as a save of one type always has;
   the page names them before Save. A type no box of which is changed is never sent.
   What is not saved is state.setup.reqDraft: the boxes the person changed (edits: type -> document -> ticked or not), the types to follow all
   companies again (follows) and the reason, for one company (or every company) and one month. Only what differs from what the server holds
   is kept, so a page read again keeps the person's boxes and takes every other box from the records; it says which changed types the records
   have moved under. Changing For or the month, and every way off the page, asks Discard your changes? first (rqMayLeave: core/router.js and
   core/events.js ask it; this file for the two pickers). Names are the person's own text: all are escaped.
   state.setup: reqScope (a company, or null for every company), reqMonth (the month picked, or null for the one the server offers), req (the
   view on show), reqOpen (types whose Earlier sets are open), reqSaving, reqMsg (messages), reqResult (what the last save did), reqImpact
   (what the boxes not saved would do to open payments, asked of the server as a preview). */
const RQ = { timer: null, leaving: null };
const RQ_PATH = "/api/setup/required";

const rqOnPage = () => state.view === "setup" && state.setup.kind === "required";
// The grid on show is the one state.setup.req describes: only then is a box clicked or a save sent (core/page.js: not while a page is read).
const rqLive = () => rqOnPage() && pageWhole() && !!state.setup.req && !state.setup.reqSaving;
const rqCompany = d => d.scope == null ? null : state.meta.entities.find(e => e.id === +d.scope) || null;
const rqCode = id => state.meta.entities.find(e => e.id === +id)?.code || "one company";
const rqType = (d, key) => (d?.types || []).find(t => t.key === key) || null;
const rqDocInfo = (d, key) => (d?.doc_types || []).find(x => x.key === key) || null;
const rqDocName = (d, key) => rqDocInfo(d, key)?.label || docLabel(key);
const rqShort = label => String(label).split(" (")[0];
const rqOffered = (d, key) => !!rqDocInfo(d, key) && isActive(rqDocInfo(d, key));
// A company Kept here is not asked for the documents SQL Account issues (rulebook.required_docs).
const rqNotAsked = (d, key) => { const co = rqCompany(d); return !!co && !co.uses_sql && !!+(rqDocInfo(d, key)?.from_sql || 0); };
const rqRows = d => [...d.types.filter(isActive), ...d.types.filter(t => !isActive(t))];
// The board's glyphs for the payment types and documents the app comes with; one added in Setup has the plain document's.
const RQ_TYPE_GLYPH = { salary: "users", director: "person", consultant: "person", statutory: "vault", utility: "receipt", rental: "receipt",
  claim: "claim", claim_overseas: "claim", transfer: "coins", receipt: "coins", other: "document" };
const RQ_DOC_GLYPH = { pv: "database", jv: "database", or: "document", invoice: "receipt", bank: "bank", einvoice: "document", portal: "check",
  claim: "claim", approval: "approval", payroll: "payroll", payslip: "users", other: "document" };
const rqGlyph = (glyphs, key) => Object.hasOwn(glyphs, key) ? glyphs[key] : "document";
// The document types in use, in pack order, and any other a set shown asks for (one stopped since): a document asked for is never off the grid.
function rqColumns(d) {
  const cols = (d.doc_types || []).filter(isActive).map(x => x.key);
  for (const x of d.doc_types || []) if (!cols.includes(x.key) && d.types.some(t => t.at.docs.includes(x.key) || t.at.follow?.includes(x.key))) cols.push(x.key);
  for (const t of d.types) for (const k of [...t.at.docs, ...(t.at.follow || [])]) if (!cols.includes(k)) cols.push(k);
  const short = cols.map(k => rqShort(rqDocName(d, k)));
  return cols.map((key, i) => ({ key, full: rqDocName(d, key), name: short.indexOf(short[i]) === short.lastIndexOf(short[i]) ? short[i] : rqDocName(d, key) }));
}
// Why a box can't be changed, or "".
function rqLocked(d, key) {
  if (!rqOffered(d, key)) return `${rqShort(rqDocName(d, key))} is no longer in use, so no new set can ask for it. A row you change leaves it out.`;
  if (rqNotAsked(d, key)) return `${rqShort(rqDocName(d, key))} is issued by SQL Account, so it isn't asked for while ${rqCompany(d).code} is Kept here. Its box stays as it is.`;
  return "";
}

/* ---- what is not saved ---- */
const rqEdited = draft => draft ? [...new Set([...Object.keys(draft.edits), ...Object.keys(draft.follows)])] : [];
// Boxes changed, and each type that is to follow all companies again counted once. The boxes ticked on such a type before are kept for
// Keep its own set, and count again only once that is pressed.
const rqCount = draft => draft ? Object.entries(draft.edits).reduce((n, [k, x]) => n + (draft.follows[k] ? 0 : Object.keys(x).length), 0) + Object.keys(draft.follows).length : 0;
const rqHeld = () => { const draft = state.setup.reqDraft; return !!draft && (rqEdited(draft).length > 0 || !!draft.reason.trim()); };
const rqDraftFor = d => state.setup.reqDraft ||= { scope: d.scope ?? null, month: d.month, edits: {}, follows: {}, seen: {}, names: {}, reason: "" };
// What a type's row was when it was changed: a page read again says when the records have moved under it.
const rqSeen = at => JSON.stringify([at.docs, at.own, at.follows_other, at.later, at.returns, at.follow, at.every_later]);
function rqNoted(draft, t) { draft.names[t.key] = t.label; draft.seen[t.key] ||= rqSeen(t.at); }
function rqTidy(draft, key) {
  if (draft.edits[key] && !Object.keys(draft.edits[key]).length) delete draft.edits[key];
  if (!draft.edits[key] && !draft.follows[key]) delete draft.seen[key];
  if (!rqEdited(draft).length && !draft.reason.trim() && state.setup.reqDraft === draft) state.setup.reqDraft = null;
}
// Whether a box shows ticked: as the records have it, or as the person left it; for a type to follow all companies again, what that gives.
// Where that is what Other needs, it is Other as the same save leaves it: following all companies too, changed here, or as the records
// have it.
function rqTicked(d, draft, t, key) {
  if (draft?.follows[t.key]) {
    const other = t.at.follow_other ? rqType(d, "other") : null;
    if (!other) return !!t.at.follow?.includes(key);
    if (draft.follows.other) return !!other.at.follow?.includes(key);
    return draft.edits.other ? rqDocsFor(d, draft, other).includes(key) : other.at.docs.includes(key);
  }
  return draft?.edits[t.key]?.[key] ?? t.at.docs.includes(key);
}
const rqChanged = (d, draft, t, key) => rqTicked(d, draft, t, key) !== t.at.docs.includes(key);
// A changed type's new set: the documents it had that stay ticked, in their order, then those newly ticked in pack order (the server compares
// the lists as they are). A document no longer in use can't be listed again.
function rqDocsFor(d, draft, t) {
  const on = k => rqOffered(d, k) && rqTicked(d, draft, t, k), had = t.at.docs;
  return [...had.filter(on), ...(d.doc_types || []).map(x => x.key).filter(k => !had.includes(k) && on(k))];
}
// What Save sends: each changed type with what the page showed for it. No other type.
function rqBody(d, draft) {
  return { entity_id: d.scope ?? null, from_month: d.month, changes: rqRows(d).filter(t => rqEdited(draft).includes(t.key))
    .map(t => ({ payment_type: t.key, docs: draft.follows[t.key] ? null : rqDocsFor(d, draft, t), was: t.at })) };
}
// The records were read again: only what still differs from them is kept. Returns what to tell the person.
function rqRebase(d) {
  const S = state.setup, draft = S.reqDraft, said = [], month = monthName(d.month);
  if (!draft) return said;
  for (const key of rqEdited(draft)) {
    const t = rqType(d, key);
    if (!t) { delete draft.edits[key]; delete draft.follows[key]; delete draft.seen[key]; said.push(`${draft.names[key] || key} is no longer a payment type, so its boxes that weren't saved were dropped.`); continue; }
    const moved = draft.seen[key] !== rqSeen(t.at);
    if (draft.follows[key] && !t.at.can_follow) {  // the boxes ticked before it were of the set that has gone: they don't come back
      said.push(`${t.label} has no set of its own left from ${month}, so Follow all companies again was taken off it${draft.edits[key] ? ", with the boxes ticked on it before" : ""}.`);
      delete draft.follows[key]; delete draft.edits[key];
    }
    for (const [doc, on] of Object.entries(draft.edits[key] || {})) {
      const lock = rqLocked(d, doc);
      if (lock) { delete draft.edits[key][doc]; said.push(`A box of ${t.label} that wasn't saved was dropped. ${lock}`); }
      else if (on === t.at.docs.includes(doc)) delete draft.edits[key][doc];  // the records have it so now
    }
    rqTidy(draft, key);
    if (moved && (draft.edits[key] || draft.follows[key])) { said.push(`What is required from ${month} for ${t.label} changed since you ticked it. Check its row before you save.`); draft.seen[key] = rqSeen(t.at); }
  }
  if (!rqEdited(draft).length && !draft.reason.trim()) S.reqDraft = null;
  return said;
}

/* ---- the words ---- */
// The months a set was in force: from from_month until to_month, the month the next set took over (either end open): reqRange, setup-paste.js.
const rqSince = at => at.follows_other ? "Same as Other" : !at.since || at.since === "0000-00" ? "From the start" : `Since ${monthName(at.since)}`;
const rqWho = id => id == null ? "all companies" : rqCode(id);
const rqFiled = d => !!d.first_allowed && d.month < d.first_allowed;
const rqFiledText = d => `${monthName(shiftMonth(d.first_allowed, -1))} is filed, and filed months never change. Choose ${monthName(d.first_allowed)} or later.`;
// What a save did to the open payments, in words.
function reqAffected(a = {}) {
  const miss = +a.now_missing || 0, done = +a.now_complete || 0, s = n => n === 1 ? "" : "s", is = n => n === 1 ? "is" : "are";
  if (!miss && !done) return "Saved. No open payment changes status.";
  const m = miss ? `${miss} open payment${s(miss)} now miss${miss === 1 ? "es" : ""} a document` : "";
  const c = !done ? "" : miss ? `${done} ${is(done)} now complete` : `${done} open payment${s(done)} ${is(done)} now complete`;
  return `Saved. ${[m, c].filter(Boolean).join("; ")}.`;
}
// The same before it is saved.
function rqImpactText(a = {}) {
  const miss = +a.now_missing || 0, done = +a.now_complete || 0, s = n => n === 1 ? "" : "s";
  if (!miss && !done) return "No open payment changes status.";
  const m = miss ? `${miss} open payment${s(miss)} will miss a document` : "";
  const c = !done ? "" : miss ? `${done} will be complete` : `${done} open payment${s(done)} will be complete`;
  return `${[m, c].filter(Boolean).join("; ")}.`;
}
// For every company: the companies in use with their own set of a type, in the month shown or later (own_in: the spans they have it in).
const rqOwnIn = t => (t.own_in || []).filter(x => isActive(state.meta.entities.find(e => e.id === x.entity_id) || { active: 0 }));
// Those months in words, "" for a set in force with no end: "until June 2027", "from March 2027", "from March 2027 until June 2027".
const rqSpans = spans => andList(spans.map(s => [s.from_month ? `from ${monthName(s.from_month)}` : "", s.to_month ? `until ${monthName(s.to_month)}` : ""].filter(Boolean).join(" ")).filter(Boolean));
// The months outside them, which a change for every company does reach.
function rqReached(spans) {
  const out = spans[0].from_month ? [`before ${monthName(spans[0].from_month)}`] : [];
  spans.forEach((s, i) => { if (s.to_month) out.push(`from ${monthName(s.to_month)}${spans[i + 1] ? ` until ${monthName(spans[i + 1].from_month)}` : ""}`); });
  return andList(out);
}
// What a save would do that the changed boxes don't show by themselves.
function rqWarnings(d, draft) {
  const out = [], co = rqCompany(d), month = monthName(d.month), changed = rqRows(d).filter(t => rqEdited(draft).includes(t.key));
  const names = list => andList(list.map(t => t.label));
  for (const t of changed) {
    if (t.at.later.length) out.push(`Saving from ${month} also replaces the later ${t.at.later.length === 1 ? "set" : "sets"} of ${t.label} (from ${andList(t.at.later.map(x => monthName(x.from_month)))}).`);
    // A company's new set of its own runs on with no end: over a month it was to follow all companies again from, and over their later sets.
    if (co && !draft.follows[t.key]) {
      if (t.at.returns?.length) out.push(`${co.code} was to follow all companies again for ${t.label} from ${andList(t.at.returns.map(monthName))}. Saving from ${month} does away with that: its own set carries on.`);
      const theirs = t.at.every_later || [];
      if (theirs.length) out.push(`All companies have another set for ${t.label} from ${andList(theirs.map(monthName))}. ${co.code} keeps its own set then too.`);
    }
    const gone = draft.follows[t.key] ? [] : t.at.docs.filter(k => !rqOffered(d, k)).map(k => rqShort(rqDocName(d, k)));
    if (gone.length) out.push(`${andList(gone)} ${gone.length === 1 ? "is" : "are"} no longer in use, so ${gone.length === 1 ? "it is" : "they are"} left out of the new set of ${t.label}.`);
    for (const x of rqOwnIn(t)) {
      const has = `${rqCode(x.entity_id)} has its own set for ${t.label}`, from = x.spans[0].from_month;
      out.push(x.spans.some(s => s.to_month) ? `${has} ${rqSpans(x.spans)}. This change reaches it ${rqReached(x.spans)}.`
        : `${has}${from ? ` from ${monthName(from)}, so from then` : ", so"} this change doesn't reach it.`);
    }
  }
  if (changed.some(t => t.key === "other")) {
    const along = rqRows(d).filter(t => draft.follows[t.key] ? t.at.follow_other : t.at.follows_other && !draft.edits[t.key]);
    if (along.length) out.push(`${names(along)} ${along.length === 1 ? "has no set of its own and needs" : "have no set of their own and need"} what Other needs, so this changes ${along.length === 1 ? "it" : "them"} too.`);
  }
  // For one company: each type that gets its own set. For every company: each that needed what Other needs, which from then on it doesn't.
  const fresh = changed.filter(t => !draft.follows[t.key] && (co ? !t.at.own : t.at.follows_other)), one = fresh.length === 1;
  if (fresh.length) out.push(co ? `Saving gives ${co.code} its own set for ${names(fresh)} from ${month}.`
    : `Saving gives ${names(fresh)} ${one ? "a set of its own" : "sets of their own"} from ${month}, so later changes to Other no longer reach ${one ? "it" : "them"}.`);
  return out;
}

/* ---- the markup ---- */
// The payroll months to pick: from the first one not filed (with nothing filed, two years back) to a year past the latest in use. The last
// filed month is listed and can't be picked.
function rqMonths(d) {
  const dated = d.types.flatMap(t => (t.history || []).map(h => h.from_month)).filter(m => m > "0000-00");
  const from = d.first_allowed || [shiftMonth(d.default_from, -24), ...dated].sort()[0], to = shiftMonth([d.default_from, d.month, ...dated].sort().pop(), 12);
  const out = d.first_allowed ? [shiftMonth(d.first_allowed, -1)] : [];
  for (let m = from; m <= to && out.length < 600; m = shiftMonth(m, 1)) out.push(m);
  if (!out.includes(d.month)) out.push(d.month);
  return out.sort().map(m => { const filed = !!d.first_allowed && m < d.first_allowed;
    return `<option value="${esc(m)}"${m === d.month ? " selected" : ""}${filed && m !== d.month ? " disabled" : ""}>${esc(monthName(m))}${filed ? " (filed)" : ""}</option>`; }).join("");
}
const rqSource = (d, key) => (+(rqDocInfo(d, key)?.from_sql || 0) ? `<span class="rq-src">${icon("database")}from SQL</span>` : "")
  + (key === "approval" ? `<span class="rq-src">${icon("approval")}from form</span>` : "")
  + (rqOffered(d, key) ? "" : `<span class="rq-src off">Not in use</span>`);
function rqHeadHtml(d, cols) {
  const co = rqCompany(d);
  return `<tr><th scope="col" class="rq-type">Payment type</th>${cols.map(c => `<th scope="col" class="rq-doc${rqNotAsked(d, c.key) ? " na" : ""}" title="${esc(c.full)}"><span class="rq-dh">${icon(rqGlyph(RQ_DOC_GLYPH, c.key), "rq-hg")}<span>${esc(c.name)}</span>${rqSource(d, c.key)}</span></th>`).join("")}<th scope="col">In force</th><th scope="col">${co ? `For ${esc(co.code)}` : "Companies"}</th></tr>`;
}
// One box: a button that is pressed while the document is required. Its label says the type, the document and everything its looks say.
function rqBoxHtml(d, draft, t, col, r, c) {
  const on = rqTicked(d, draft, t, col.key), changed = rqChanged(d, draft, t, col.key), form = col.key === "approval";
  const na = rqNotAsked(d, col.key), gone = !rqOffered(d, col.key), co = rqCompany(d);
  const off = state.setup.reqSaving || !!rqLocked(d, col.key) || !!draft?.follows[t.key];
  const words = [on ? "required" : "not needed", on && form ? "from an approved form" : "", na ? `issued by SQL Account, so not asked for while ${co.code} is Kept here` : "",
    gone ? "no longer in use" : "", changed ? "changed, not saved yet" : ""].filter(Boolean).join(", ");
  const tip = changed ? "Changed, not saved yet" : na ? `Issued by SQL Account, so not asked for while ${co.code} is Kept here` : gone ? "No longer in use" : "";
  return `<td class="rq-cell${na ? " na" : ""}"><button type="button" class="rq-box${on ? " on" : ""}${changed ? " changed" : ""}${na || gone ? " off" : ""}" id="rq-c-${r}-${c}" data-rq-type="${esc(t.key)}" data-rq-doc="${esc(col.key)}" data-rq-r="${r}" data-rq-c="${c}" aria-pressed="${on}"${off ? ` aria-disabled="true"` : ""} aria-label="${esc(`${t.label}: ${col.full}, ${words}`)}"${tip ? ` title="${esc(tip)}"` : ""}>${on ? icon(form ? "approval" : "check") : ""}${changed ? `<span class="rq-dot" aria-hidden="true"></span>` : ""}</button></td>`;
}
// A type's last column: for a company, whether the set is its own, with Follow all companies again; for every company, who has their own.
function rqForHtml(d, draft, t, r) {
  const co = rqCompany(d), busy = state.setup.reqSaving ? ` aria-disabled="true"` : "";
  if (!co) {
    return rqOwnIn(t).map(x => { const months = rqSpans(x.spans); return `<span class="pill">${esc(rqCode(x.entity_id))} has its own set${months ? ` ${esc(months)}` : ""}</span>`; }).join("");
  }
  const button = (on, words, label) => `<button type="button" class="link rq-act" id="rq-f-${r}" data-rq-type="${esc(t.key)}" data-rq-follow="${on}" aria-label="${esc(label)}"${busy}>${words}</button>`;
  if (draft?.follows[t.key]) return `<span class="pill grey">Will follow all companies</span>${button("0", "Keep its own set", `Keep its own set for ${t.label}`)}`;
  const tag = t.at.own ? `<span class="pill">Its own set</span>` : t.at.later.length ? `<span class="pill">Its own set from ${esc(monthName(t.at.later[0].from_month))}</span>` : `<span class="pill grey">Follows all companies</span>`;
  return tag + (t.at.can_follow ? button("1", "Follow all companies again", `Follow all companies again for ${t.label}`) : "");
}
// Every dated set of a type this scope can meet, newest first, the one in force in the month marked.
function rqSetsHtml(d, t) {
  const hs = t.history || [], at = t.at, mine = at.own ? +d.scope : null;
  const covers = h => h.from_month <= d.month && (!h.to_month || d.month < h.to_month);
  const line = h => `<div>${esc(reqRange(h))}, ${esc(rqWho(h.entity_id))}: ${h.docs?.length ? h.docs.map(k => esc(rqDocName(d, k))).join(", ") : "none"}${!at.follows_other && covers(h) && h.entity_id === mine ? ` <span class="muted">(in force in ${esc(monthName(d.month))})</span>` : ""}</div>`;
  const only = hs.length === 1 && hs[0].from_month === "0000-00" && !hs[0].to_month;
  return `<b>Earlier sets for ${esc(t.label)}</b>${at.follows_other ? `<div>This type has no documents set of its own from ${esc(monthName(d.month))}, so it needs what Other needs.</div>` : ""}${only ? `<div>No earlier sets: this set has been in force from the start.</div>` : ""}${hs.length ? hs.map(line).join("") : `<div class="muted">No set of its own is recorded.</div>`}`;
}
// The first later month from which another set is in force for a row, or none: as the records have it; for a type to follow all companies
// again, as it is once it does. Where that is what Other needs and the same save changes Other too, the records don't say.
function rqNext(draft, t) {
  if (!draft?.follows[t.key]) return t.at.changes_from;
  return t.at.follow_other && (draft.follows.other || draft.edits.other) ? null : t.at.follow_changes_from;
}
function rqBodyHtml(d) {
  const S = state.setup, draft = S.reqDraft, cols = rqColumns(d), span = cols.length + 3;
  const rows = rqRows(d).map((t, r) => {
    // the documents its payments are asked for: not a greyed box of SQL Account's for a company Kept here
    const n = cols.filter(c => !rqNotAsked(d, c.key) && rqTicked(d, draft, t, c.key)).length, open = !!S.reqOpen?.[t.key], next = rqNext(draft, t);
    return `<tr${isActive(t) ? "" : ` class="rq-stopped"`}><th scope="row" class="rq-type"><div class="rq-th">${icon(rqGlyph(RQ_TYPE_GLYPH, t.key), "rq-tg")}<div><span class="rq-name">${esc(t.label || t.key)}</span>${t.direction === "in" ? ` <span class="pill ok">Money in</span>` : ""}${isActive(t) ? "" : ` <span class="pill grey">Stopped</span>`}<span class="rq-n">${plural(n, "document")}</span></div></div></th>
      ${cols.map((c, i) => rqBoxHtml(d, draft, t, c, r, i)).join("")}
      <td class="rq-since"><span>${esc(draft?.follows[t.key] ? "Follows all companies" : rqSince(t.at))}</span>${next ? `<span class="note">Changes from ${esc(monthName(next))}</span>` : ""}<button type="button" class="link rq-act" id="rq-h-${r}" data-rq-type="${esc(t.key)}" data-rq-hist="1" aria-expanded="${open}" aria-label="${esc(`Earlier sets for ${t.label}`)}"><span class="rq-chev" aria-hidden="true">${icon("chevronRight")}</span>Earlier sets</button></td>
      <td class="rq-for">${rqForHtml(d, draft, t, r)}</td></tr>${open ? `<tr class="rq-hist"><td colspan="${span}"><div class="rq-hist-in">${rqSetsHtml(d, t)}</div></td></tr>` : ""}`;
  }).join("");
  return rows || `<tr><td colspan="${span}" class="empty">No payment types yet.</td></tr>`;
}
// The status line over the grid: what is not saved and what saving it would do, a message, and what the last save did.
function rqStatusHtml() {
  const S = state.setup, d = S.req, draft = S.reqDraft, n = rqCount(draft);
  let out = "";
  if (n) {
    const notes = rqWarnings(d, draft);
    out += `<div class="rq-strip warn">${icon("edit")}<b>${n} unsaved change${n === 1 ? "" : "s"}</b><span>${esc(S.reqSaving ? "Saving…" : S.reqImpact?.text || "")}</span>${notes.length ? `<ul>${notes.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}</div>`;
  }
  out += (S.reqMsg || []).map(x => `<div class="rq-strip msg">${icon("alert")}<span>${esc(x)}</span></div>`).join("");
  if (S.reqResult) out += `<div class="rq-strip ok">${icon("check")}<span>${esc(S.reqResult)}</span><button type="button" class="ghost small" data-rq-dismiss="1">Dismiss</button></div>`;
  return out;
}
function rqLegendHtml(d) {
  const keys = (d.doc_types || []).filter(isActive), sql = keys.some(x => +x.from_sql), form = keys.some(x => x.key === "approval");
  return `<div class="rq-legend"><span><span class="rq-box on sample" aria-hidden="true">${icon("check")}</span>Required</span>
    <span><span class="rq-box changed sample" aria-hidden="true"><span class="rq-dot"></span></span>Changed, not saved yet</span>
    ${sql ? `<span><span class="rq-src">${icon("database")}from SQL</span>This document is issued by SQL Account.</span>` : ""}
    ${form ? `<span><span class="rq-src">${icon("approval")}from form</span>An approved form fills this box once Approvals is built. Until then the form is uploaded by hand.</span>` : ""}
    <span>Click a box to change it. Save applies each changed type from the month you picked.</span></div>`;
}
function rqPageHtml(d) {
  const S = state.setup, co = rqCompany(d), live = state.meta.entities.filter(isActive), cols = rqColumns(d), month = monthName(d.month);
  const sqlDocs = (d.doc_types || []).filter(x => +x.from_sql && isActive(x)).map(x => rqShort(x.label || x.key)), sqlIssued = andList(sqlDocs.map(esc)), many = sqlDocs.length > 1;
  const kept = !co ? "" : `<p class="rq-scope-note">${icon("help")}<span>${esc(co.code)} is ${esc(keptLabel(co))}: ${co.uses_sql ? "its payment vouchers are issued by SQL Account and read in on the SQL import page."
    : sqlIssued ? `${sqlIssued} ${many ? "are" : "is"} issued by SQL Account, so ${many ? "they are" : "it is"} not asked for while ${esc(co.code)} is Kept here. ${many ? "Their boxes are" : "Its boxes are"} greyed and stay as they are. Every other document a type needs is asked for.`
    : "nothing a type needs is issued by SQL Account, so every document in the grid is asked for."}</span></p>`;
  return `${setupHead("required", setupSpec(), { intro: "What each payment type needs before it counts as Complete. A change applies from the payroll month you pick and never reaches a filed month." })}
    <div class="rq">
    <form class="rq-bar noprint" id="reqForm" novalidate>
      <label class="field"><span>For</span><select id="rq-scope"><option value="all"${co ? "" : " selected"}>Every company</option>${live.map(e => `<option value="${e.id}"${co?.id === e.id ? " selected" : ""}>${esc(e.code)} only</option>`).join("")}</select></label>
      <label class="field"><span>From payroll month</span><select id="rq-month" aria-describedby="rq-month-note">${rqMonths(d)}</select></label>
      <label class="field rq-why"><span>Why are you making this change? (optional)</span><input id="rq-reason" maxlength="500" autocomplete="off" value="${esc(S.reqDraft?.reason || "")}" placeholder="Kept in the audit trail with the change"></label>
      <div class="rq-go"><button type="button" class="ghost" id="rq-discard" data-rq-discard="1">Discard</button><button type="submit" class="btn" id="rq-save" aria-describedby="rq-impact">Save from ${esc(month)}</button></div>
    </form>
    ${kept}
    <p class="note" id="rq-month-note">${esc(rqFiled(d) ? rqFiledText(d) : `Applies from ${month}. It never reaches a filed month.${co ? ` ${co.code} follows the documents set for all companies, unless it has its own set for a type.` : ""}`)}</p>
    <div id="rq-impact" role="status">${rqStatusHtml()}</div>
    <section class="card rq-card" aria-label="The documents each payment type needs">
      ${(d.doc_types || []).some(isActive) ? "" : `<p class="note">No document types in use.</p>`}
      <div class="rq-wrap"><table class="rq-table"><thead>${rqHeadHtml(d, cols)}</thead><tbody id="rq-body">${rqBodyHtml(d)}</tbody></table></div>
      ${rqLegendHtml(d)}</section></div>`;
}

/* ---- drawing ---- */
async function setupRequired(box) {
  const S = state.setup, live = state.meta.entities.filter(isActive), said = [];
  const scope = live.some(e => e.id === S.reqScope) ? S.reqScope : null;
  const asked = (S.reqDraft && S.reqDraft.scope === scope ? S.reqDraft.month : null) || S.reqMonth;
  const read = month => api(`${RQ_PATH}?entity=${scope ?? ""}${month ? `&month=${month}` : ""}`);
  let d = await read(asked);
  if (!(box = setupBox(box))) return;
  // A month picked that has been filed since, with nothing waiting on it: the month the server offers instead.
  if (asked && !(S.reqDraft && S.reqDraft.scope === scope) && rqFiled(d)) {
    d = await read(null);
    if (!(box = setupBox(box))) return;
    S.reqMonth = null;
    said.push(`${monthName(asked)} can't be picked now that a month is filed, so the grid shows ${monthName(d.month)}.`);
  }
  // Boxes never go over to another company or month: with the company they were for gone, they go, and it is said.
  if (S.reqDraft && (S.reqDraft.scope !== (d.scope ?? null) || S.reqDraft.month !== d.month)) {
    if (rqHeld()) said.push(`The boxes that weren't saved were for ${rqWho(S.reqDraft.scope)} from ${monthName(S.reqDraft.month)}, which can't be shown now, so they were dropped.`);
    S.reqDraft = null;
  }
  S.reqScope = scope; S.req = d; S.reqOpen ||= {};
  if (!S.reqSaving) said.push(...rqRebase(d));  // while a save is on its way, what it sent stays as it is
  if (said.length) S.reqMsg = [...new Set([...(S.reqMsg || []), ...said])];
  S.reqImpact = null;
  box.innerHTML = rqPageHtml(d);
  rqControls();
  rqImpactSoon();
}
// What the pickers, the reason box and the two buttons allow now.
function rqControls() {
  const S = state.setup, busy = !!S.reqSaving, set = (id, fn) => { const el = $("#" + id); if (el) fn(el); };
  set("rq-scope", el => { el.disabled = busy; });
  set("rq-month", el => { el.disabled = busy; });
  set("rq-reason", el => { el.readOnly = busy; });
  set("rq-discard", el => { el.disabled = busy || !rqHeld(); });
  set("rq-save", el => {
    el.disabled = busy;
    if (busy) el.setAttribute("aria-busy", "true"); else el.removeAttribute("aria-busy");
    el.innerHTML = busy ? `<span class="spin" aria-hidden="true"></span>Saving…` : `Save from ${esc(monthName(S.req.month))}`;
  });
}
function rqPaintStatus() { const el = $("#rq-impact"); if (el && rqOnPage() && state.setup.req) el.innerHTML = rqStatusHtml(); }
// The rows and the status line again; a box or a row's button that had the focus keeps it.
function rqPaint() {
  const rows = $("#rq-body");
  if (!rows || !rqOnPage() || !state.setup.req) return;
  const on = document.activeElement?.id || "";
  rows.innerHTML = rqBodyHtml(state.setup.req);
  if (/^rq-[chf]-/.test(on)) document.getElementById(on)?.focus?.({ preventScroll: true });
  rqPaintStatus();
  rqControls();
}
// What the boxes not saved would do to open payments: asked of the server, which makes the save and undoes it. Asked again only when they change.
function rqImpactSoon() {
  const S = state.setup, d = S.req, draft = S.reqDraft;
  if (!d || !draft || !rqEdited(draft).length || S.reqSaving || rqFiled(d)) { clearTimeout(RQ.timer); S.reqImpact = null; return rqPaintStatus(); }
  const body = rqBody(d, draft), key = JSON.stringify(body);
  if (S.reqImpact?.key === key) return;
  clearTimeout(RQ.timer);
  S.reqImpact = { key, text: "Working out what changes for open payments…" };
  rqPaintStatus();
  RQ.timer = setTimeout(() => rqImpactRead(key, body), 300);
}
function rqImpactRead(key, body) {
  pageDraw("reqImpact", async page => {
    const r = await page.read(api(RQ_PATH, { json: { ...body, preview: true } }).catch(e => ({ error: e })));
    if (state.setup.reqImpact?.key !== key) return;  // the boxes have changed since it was asked
    state.setup.reqImpact.text = r.error ? `The effect on open payments couldn't be worked out. ${errorWords(r.error)}` : rqImpactText(r.affected);
    rqPaintStatus();
  }).catch(e => toast(e.message, true));
}

/* ---- the boxes ---- */
function rqToggle(typeKey, doc) {
  if (!rqLive()) return;
  const S = state.setup, d = S.req, t = rqType(d, typeKey);
  if (!t) return;
  const why = S.reqDraft?.follows[typeKey] ? `${t.label} will follow all companies again when you save. Press Keep its own set to change its boxes.` : rqLocked(d, doc);
  S.reqResult = "";
  if (why) { S.reqMsg = [why]; return rqPaint(); }
  const draft = rqDraftFor(d), on = !rqTicked(d, draft, t, doc);
  rqNoted(draft, t);
  const edits = draft.edits[typeKey] ||= {};
  if (on === t.at.docs.includes(doc)) delete edits[doc]; else edits[doc] = on;  // as the records have it: not a change
  rqTidy(draft, typeKey);
  S.reqMsg = [];
  rqPaint();
  rqImpactSoon();
}
// Follow all companies again (on), or keep the company's own set after all.
function rqFollow(typeKey, on) {
  if (!rqLive()) return;
  const S = state.setup, d = S.req, t = rqType(d, typeKey);
  if (!t || on && !t.at.can_follow) return;
  const draft = rqDraftFor(d);
  rqNoted(draft, t);
  if (on) draft.follows[typeKey] = true; else delete draft.follows[typeKey];  // boxes ticked before stay, for Keep its own set
  rqTidy(draft, typeKey);
  S.reqMsg = []; S.reqResult = "";
  rqPaint();
  rqImpactSoon();
}
function rqHistory(typeKey) {
  if (!rqOnPage() || !state.setup.req) return;
  const open = state.setup.reqOpen ||= {};
  open[typeKey] = !open[typeKey];
  rqPaint();
}
function rqDismiss() { state.setup.reqResult = ""; rqPaintStatus(); $("#rq-save")?.focus?.({ preventScroll: true }); }
// Drops what isn't saved, with its messages and the preview.
function rqDrop() {
  const S = state.setup;
  S.reqDraft = null; S.reqMsg = []; S.reqResult = ""; S.reqImpact = null;
  clearTimeout(RQ.timer); pageDrop("reqImpact");
  const reason = $("#rq-reason"); if (reason) reason.value = "";
}
function rqDiscard() {
  if (state.setup.reqSaving || !rqOnPage()) return;
  rqDrop();
  rqPaint();
  $("#rq-save")?.focus?.({ preventScroll: true });
}
// The grid is no longer the page on show (setupLeft, or another Setup section): nothing of it is kept but For.
function rqLeft() { rqDrop(); state.setup.reqMonth = null; state.setup.reqOpen = {}; }

/* ---- leaving ---- */
// Asked before anything that would take the boxes off the page: true when there is nothing to lose or you let it go. Two asks at once share one
// dialog. While a save is on its way it says so instead: what was sent is saved or refused whatever you do.
function rqMayLeave() {
  if (!rqHeld()) return Promise.resolve(true);
  const S = state.setup, n = rqCount(S.reqDraft);
  RQ.leaving ||= (S.reqSaving
    ? ask("Your changes are being saved. If you leave now you are told whether they were kept. If they are refused, your boxes are not kept.",
      { title: "Leave while saving?", yes: "Leave", no: "Stay here", tone: "warn", glyph: "edit" })
    : ask(`${n ? `${plural(n, "unsaved change")} on Required documents` : "The reason typed on Required documents"} will be lost.`,
      { title: "Discard your changes?", yes: "Discard changes", no: "Keep editing", danger: true, tone: "warn", glyph: "edit" }))
    .then(yes => { if (yes) rqDrop(); return yes; }).finally(() => { RQ.leaving = null; });
  return RQ.leaving;
}
// What has the focus on the grid, by its id, or "".
const rqFocusAt = () => { const id = document.activeElement?.id || ""; return /^rq-/.test(id) ? id : ""; };
// Runs draw, which reads and draws the grid again and so replaces what had the focus there: it goes back to the same box or button, else to
// Save. from: where it was before, for a browser that takes the focus off a button as it is turned off. It is never taken from what has it.
async function rqKeepFocus(from, draw) {
  const on = rqFocusAt() || from;
  const ok = await draw();
  if (on && rqOnPage() && focusLost()) {
    const el = document.getElementById(on);
    (el && !el.disabled ? el : $("#rq-save"))?.focus?.({ preventScroll: true });
  }
  return ok;
}
// For or the month was picked: another company's or month's grid, asking first when something isn't saved. Boxes never go over to it.
async function rqPick(el) {
  const S = state.setup, d = S.req, month = el.id === "rq-month";
  const was = d ? String(month ? d.month : d.scope ?? "all") : el.value;
  if (!rqOnPage() || S.reqSaving) { el.value = was; return; }
  const value = el.value;
  if (rqHeld() && !(await rqMayLeave())) { el.value = was; return; }
  if (!rqOnPage()) return;
  rqDrop();
  if (month) S.reqMonth = value; else S.reqScope = value === "all" ? null : +value;
  await rqKeepFocus(el.id, () => render());
}

/* ---- saving ---- */
// Every changed type, in one request. A refused save keeps the boxes and the reason, and the grid is read again so that what it holds is on show.
async function rqSave() {
  const S = state.setup, d = S.req;
  if (!rqLive()) return;
  const draft = S.reqDraft;
  const stop = rqFiled(d) ? rqFiledText(d) : !draft || !rqEdited(draft).length ? "Nothing changes: these are the documents already required from that month." : "";
  if (stop) { S.reqMsg = [stop]; S.reqResult = ""; return rqPaint(); }
  const body = rqBody(d, draft), reason = draft.reason.trim(), month = d.month, from = rqFocusAt();  // before Save is turned off
  if (reason) body.reason = reason;
  S.reqSaving = true; S.reqMsg = []; S.reqResult = ""; S.reqImpact = null;
  clearTimeout(RQ.timer); pageDrop("reqImpact");
  rqPaint();
  let r;
  try { r = await api(RQ_PATH, { json: body }); }
  catch (e) { S.reqSaving = false; return rqRefused(e, draft, from); }
  S.reqSaving = false;
  const mine = S.reqDraft === draft, said = reqAffected(r.affected);
  if (mine) S.reqDraft = null;  // before the reading back, so the grid read back shows nothing as not saved
  if (!rqOnPage()) return toast(`Required documents saved from ${monthName(month)}. ${said.replace(/^Saved\. /, "")}`);
  if (mine) {
    S.reqMsg = [];
    const box = $("#rq-reason"); if (box) box.value = "";
  }
  S.reqResult = said;  // said on the grid too, also when it was left and opened again meanwhile
  toast(`Saved from ${monthName(month)}`);
  return afterSaved(o => rqKeepFocus(from, () => render(o)));
}
async function rqRefused(e, draft, from) {
  const S = state.setup, words = e.unsure ? changeError(e) : /nothing was saved/i.test(e.message) ? e.message : `${e.message} Nothing was saved.`;
  const elsewhere = () => toast(e.unsure ? `Required documents: ${words}` : `Required documents wasn't saved: ${e.message}`, true);
  if (!rqOnPage()) return elsewhere();
  if (S.reqDraft !== draft) { elsewhere(); rqPaint(); return e.unsure ? rqKeepFocus("", () => render({ unsure: true })) : null; }  // left and come back: this grid is another
  // Leave while saving? may be up over this grid. What is written on the grid goes with it if you choose Leave, so it is then said in a message.
  let told = false;
  RQ.leaving?.then(left => { if (left && !told) elsewhere(); });
  S.reqMsg = [words];
  rqPaint();
  if (!(await rqKeepFocus(from, () => render(e.unsure ? { unsure: true } : undefined)))) { told = true; toast(`Required documents: ${words}`, true); }  // the page shows why it can't be read
}

document.addEventListener("change", ev => {
  if (ev.target.id === "rq-scope" || ev.target.id === "rq-month") rqPick(ev.target).catch(e => toast(e.message, true));
});
// The reason is kept as it is typed, so a page read again shows it; a reason alone is also something not saved.
document.addEventListener("input", ev => {
  const S = state.setup;
  if (ev.target.id !== "rq-reason" || !rqOnPage() || !S.req || !S.reqDraft && !pageWhole()) return;
  const draft = rqDraftFor(S.req);
  draft.reason = ev.target.value;
  if (!rqEdited(draft).length && !draft.reason.trim()) S.reqDraft = null;
  rqControls();
});
// The arrow keys move from box to box, Home and End to the ends of the row. Every box stays a stop of Tab too.
document.addEventListener("keydown", ev => {
  const ds = ev.target?.dataset;
  if (!ds || !("rqR" in ds) || ev.altKey || ev.ctrlKey || ev.metaKey || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(ev.key)) return;
  ev.preventDefault();
  let r = +ds.rqR, c = +ds.rqC;
  if (ev.key === "ArrowLeft") c--; else if (ev.key === "ArrowRight") c++; else if (ev.key === "ArrowUp") r--; else if (ev.key === "ArrowDown") r++;
  else c = ev.key === "Home" ? 0 : rqColumns(state.setup.req).length - 1;
  document.getElementById(`rq-c-${r}-${c}`)?.focus?.();
});
