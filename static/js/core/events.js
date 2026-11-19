"use strict";
/* ---------------- Events ---------------- */
document.addEventListener("click", async ev => {
  const t = ev.target.closest("button, tr[data-payment], a");
  if (!t) return;
  const ds = t.dataset;
  if (ds.sort) return sortClick(ds.sort, ds.col, t);
  try {
    if (ds.view) return go(ds.view, ds.entity);
    if (ds.goField) { ev.preventDefault(); const f = document.getElementById(ds.goField); f?.scrollIntoView?.({ block: "center" }); return f?.focus?.(); }
    if (ds.copyDetails !== undefined) return copyDetails(ds.copyDetails);
    if (ds.retry) { if (ds.busy) { t.disabled = true; t.setAttribute("aria-busy", "true"); t.innerHTML = `<span class="spin" aria-hidden="true"></span>${esc(ds.busy)}`; } return render(); }
    if (ds.histOpen) { const [tbl, key] = ds.histOpen.split(":"); return openHistory(tbl, key, ds.histTitle); }
    if (ds.restore) return await openRestore(+ds.restore, ds.restoreTitle);
    if (ds.restoreGo) return restoreGo(+ds.restoreGo, t);
    if (ds.packFile) return await openPackCheck(ds.packCheck, ds.packFile);
    if (ds.tx) return toggleEntry(+ds.tx, t);
    if (ds.trailMore) return trailMore(t);
    if (t.id === "trailCheck") return trailCheck(t);
    if (t.id === "trailAccept") return trailAccept(t);
    if (ds.pill) return pillGo(ds.pill, +ds.entity);
    if (ds.nextGo) { const r = state.next?.get(ds.nextGo); return r && goTo(r.go); }
    if (ds.older) { const [e, m] = ds.older.split(" "); return goTo({ view: "entity", entity_id: +e, month: m }); }
    if (ds.nextAll) { const k = nextScope() || 0; state.nextAll[k] = !state.nextAll[k]; return refreshNext(); }
    if (ds.savedBalance) return render();
    if (ds.nextBackup) {
      await go("settings"); $("#bkPw")?.focus();  // the password is typed there; a plain backup is not offsite
      return;
    }
    if (ds.pickEntity) { if (!(await closeDrawer())) return; state.entity = +ds.pickEntity; state.addr.id = null; state.addr.params = {}; return redraw(); }
    if (ds.fix) return fixIt(ds.fix, +ds.id);
    if (ds.closeMonth) return await markFiled(ds.closeMonth === "built");
    if (ds.reopenMonth) {
      const r = await api("/api/months/close", { json: { entity_id: state.entity, month: state.month, closed: false } });
      toast(`${monthName(state.month)} reopened.${r.pack_ticked ? " Its audit pack item stays ticked; untick it if the pack needs doing again." : ""}`); return render();
    }
    if (ds.openMonth) {
      await api("/api/months/open", { json: { entity_id: +ds.openMonth, month: state.month } });
      toast(`${monthName(state.month)} is set up`); return render();
    }
    if (t.id === "prevMonth" || t.id === "nextMonth" || t.id === "thisMonth") {
      if (!(await closeDrawer())) return;
      state.month = t.id === "thisMonth" ? currentCycle() : shiftMonth(state.month, t.id === "prevMonth" ? -1 : 1);
      state.addr.params = state.view === "bank" && state.addr.params.filter ? { filter: state.addr.params.filter } : {};  // the filters were used up; the to-explain list stays
      return redraw();
    }
    if (t.id === "closeDrawer") return closeDrawer();
    if (ds.setupKind) {
      if (!(await closeDrawer())) return;
      Object.assign(state.setup, { kind: ds.setupKind, id: null }); return redraw();
    }
    if (ds.setupNew) return await openSetup(ds.setupNew, "new");
    if (ds.setupPaste) return openPaste(ds.setupPaste);
    if (ds.pasteRead) { t.disabled = true; try { return await pasteSave(true); } finally { if (t.isConnected) t.disabled = false; } }
    if (ds.setupOpen) return await openSetup(state.setup.kind, +ds.setupOpen);
    if (ds.setupView) {
      const kind = state.setup.kind;
      state.setup.view[kind] = ds.setupView === "tree" ? "tree" : "flat";
      try { localStorage.setItem("hrp-setup-view-" + kind, state.setup.view[kind]); } catch {}
      await render();
      return document.querySelector(`[data-setup-view="${state.setup.view[kind]}"]`)?.focus({ preventScroll: true });
    }
    if (ds.tree || ds.treeAll) {
      // Opening or closing a heading or an account draws just the list again, and keeps the focus on that button.
      const kind = state.setup.kind, id = "setup-" + kind, tid = treeId(kind, state.setup.types?.kinds?.[kind]);
      const closed = state.setup.closed[tid] ||= new Set();
      if (ds.tree) closed.has(ds.tree) ? closed.delete(ds.tree) : closed.add(ds.tree);
      else if (ds.treeAll === "open") closed.clear();
      else (state.setup.treeKeys?.[tid] || []).forEach(k => closed.add(k));
      LIST_REDRAW[id]?.();
      return (ds.tree ? document.querySelector(`[data-tree="${CSS.escape(ds.tree)}"]`) : t)?.focus({ preventScroll: true });
    }
    if (ds.setupAct) return await setupAct(ds.setupAct, t);
    if (ds.whyCancel) return hideWhy();
    if (ds.reqScope) {
      if (!(await closeDrawer())) return;
      state.setup.reqScope = ds.reqScope === "all" ? null : +ds.reqScope; return render();
    }
    if (ds.reqEdit) return openRequired(ds.reqEdit);
    if (ds.reqFollow) { t.disabled = true; try { return await reqSave(true); } finally { if (t.isConnected) t.disabled = false; } }
    if (ds.chkNew) return openChecklist("new");
    if (ds.chkOpen) return openChecklist(+ds.chkOpen);
    if (ds.chkCopy) return openChkCopy();
    if (ds.chkAct) return await chkAct(ds.chkAct, t);
    if (ds.remNew) return openReminder("new");
    if (ds.remOpen) return openReminder(+ds.remOpen);
    if (ds.remAct) return await remAct(ds.remAct, t);
    if (ds.movePick) { t.disabled = true; try { return await movePick(); } finally { if (t.isConnected) t.disabled = false; } }
    if (ds.moveGo) return askWhy(t, "Import it", moveImport);
    if (ds.moveCancel) { Object.assign(state.setup.move, { file: null, preview: null }); hideWhy(); $("#mvPreview").innerHTML = ""; return; }
    if (ds.chkPreview || ds.chkCopyPreview || ds.remPreview) {
      t.disabled = true;
      try { return await (ds.chkPreview ? chkSave(true) : ds.chkCopyPreview ? chkCopySave(true) : remSave(true)); } finally { if (t.isConnected) t.disabled = false; }
    }
    if (ds.payeeAct) return await payeeAct(ds.payeeAct, +ds.payeeId, t);
    if (ds.advAdd) return await advAdd(+ds.advAdd, t);
    if (ds.advSave) return await advSave(+ds.advSave, t);
    if (ds.advDel) return advDelete(+ds.advDel, t);
    if (t.id === "printPage") return window.print();
    if (ds.payment) {
      // Clicking the open payment again keeps what was typed in it.
      const same = +ds.payment === state.openPayment && !$("#drawer").hidden;
      if (!same && !(await mayLeave())) return;
      return openPayment(+ds.payment, same ? unsavedEdits() : {});
    }
    // A payment's document box (data-upload: its type) or a checklist item's (data-task-upload, with data-type).
    if (ds.upload || ds.taskUpload) {
      const files = await pickFile(!ds.replaces); if (!files.length) return;
      if (ds.replaces && !(await ask(`Replace \u201c${ds.name}\u201d with \u201c${files[0].name}\u201d? The old file is taken out of the audit pack.`, { title: `Replace \u201c${ds.name}\u201d?`, yes: "Replace file", no: "Cancel", tone: "brand", glyph: "document", closing: "You can replace it again at any time." }))) return;
      const owner = ds.taskUpload ? { task_id: +ds.taskUpload } : { payment_id: state.openPayment };
      // awaited, so a file refused reaches the message below
      return await uploadFiles(files, { ...owner, doc_type: ds.upload || ds.type, replaces: ds.replaces });
    }
    if (t.id === "extraUpload") {
      const files = await pickFile(); if (!files.length) return;
      return await uploadFiles(files, { payment_id: state.openPayment, doc_type: $("#extraType").value });
    }
    if (ds.removeDoc) {
      if (!(await ask("It is left out of the audit pack; the file itself is kept on this PC.", { title: `Remove \u201c${ds.name}\u201d?`, yes: "Remove document", no: "Cancel", danger: true, tone: "bad", glyph: "trash", closing: "You can add the file to the payment again." }))) return;
      await api(`/api/documents/${ds.removeDoc}/remove`, { json: {} }); toast(`Removed ${ds.name}`); return render();
    }
    if (t.id === "deletePayment") {
      if (t.dataset.confirm !== "1") { t.dataset.confirm = "1"; t.textContent = "Click again to remove"; return; }
      let r;
      try { r = await api(`/api/payments/${state.openPayment}`, { method: "DELETE", json: {} }); }
      catch (e) { t.dataset.confirm = ""; t.textContent = "Remove this payment"; throw e; }
      // A voucher of a month before the first month tracked goes back under Before tracking, not under SQL entries not linked.
      const bt = r.before_tracking || [], back = r.unlinked.filter(n => !bt.includes(n));
      closeDrawer(true); toast(`Payment removed${back.length ? `; ${back.join(", ")} back under SQL entries not linked` : ""}${bt.length ? `; ${bt.join(", ")} back under Before tracking on the SQL page` : ""}${r.lines
        ? `; ${r.lines} bank line${r.lines > 1 ? "s" : ""} back under lines to explain` : ""}`); return render();
    }
    if (t.id === "addPayment") return addPaymentDrawer();
    if (ds.explain) return explainLine(+ds.explain);
    if (ds.rcAcct) { Object.assign(state.recon, { account: +ds.rcAcct, year: null, open: null, rv: null }); state.addr.params.account = String(ds.rcAcct); syncAddr(); return render(); }
    if (ds.rcYear) { Object.assign(state.recon, { year: ds.rcYear, open: null }); return drawRecon(); }
    if (ds.rcOpen) { state.recon.open = state.recon.open === ds.rcOpen ? null : ds.rcOpen; return drawRecon(); }
    if (ds.rcReview) return openReview(+ds.rcReview);
    if (ds.rvBack) { state.recon.rv = null; return drawRecon(); }
    if (ds.rvToggle) { RV().showMatched = !RV().showMatched; return drawRvList(); }
    if (ds.rvConfirmAll) {
      const r = await api("/api/recon/confirm-matched", { json: { entity_id: state.entity, statement_id: RV().sid } });
      toast(`${r.confirmed} line${r.confirmed === 1 ? "" : "s"} confirmed${r.needs_date_tick ? `; ${r.needs_date_tick} with a different date left for you to select and tick` : ""}.`);
      return reloadReview();
    }
    if (t.id === "rvApply") { t.disabled = true; try { return await rvApply(); } finally { t.disabled = false; } }
    if (ds.rcSign) return rcAct("sign-off", { statement_id: +ds.rcSign }, "Marked as reconciled.");
    if (ds.rcUndo) return rcAct("undo-sign-off", { statement_id: +ds.rcUndo }, "Sign-off undone.");
    if (ds.rcReconfirm) return rcAct("confirm-book", { statement_id: +ds.rcReconfirm }, "Sign-off confirmed again with the new book figures.");
    if (ds.rcBefore) {
      const id = ds.rcBefore, tick = document.querySelector(`[data-rc-before-tick="${id}"]`)?.checked === true;
      return rcAct("before-tracking", { statement_id: +id, checked: tick, note: document.querySelector(`[data-rc-note="${id}"]`)?.value || "" }, "Marked as reconciled before tracking.");
    }
    if (ds.unlink) {
      const r = await api(`/api/statement-lines/${ds.unlink}`, { json: { payment_id: null } });
      toast(r.removed ? `Undone. ${r.removed} was created from the bank statement and had nothing else on it, so it was removed too.` : "Undone. The line is waiting to be explained.");
      return render();
    }
    if (t.id === "sqlApply") {
      const p = state.sqlPreview; t.disabled = true;
      const links = {}; for (const r of p.records) if (r.payment_id && (!r.exists || r.kind === "invoice")) links[r.row] = r.payment_id;
      const res = await api("/api/sql/apply", { json: { token: p.token, header_row: p.header_row, mapping: p.mapping, links, journal_id: p.journal_lines?.chosen } });
      state.sqlPreview = null; delete state.sqlPaste[state.entity];
      if (res.journal_lines) { toast(`Kept ${res.journal_lines} journal lines.`); return render(); }
      const kept = res.ledger?.files || [], docs = kept.filter(f => f.kind === "journal").reduce((a, f) => a + (f.summary?.docs || 0), 0),
        diffs = kept.reduce((a, f) => a + (f.problems || 0), 0);
      const lines = kept.length ? `Kept the account lines of ${plural(docs, "document")} from ${plural(kept.length, "report")} of SQL's${diffs ? `; ${plural(diffs, "difference")} from SQL's reports, listed under Checks against SQL's reports` : ""}` : "";
      const moved = res.recon_changed?.length ? `. The bank reconciliation of signed-off ${res.recon_changed.map(m => monthName(m.month)).join(", ")} changed: it stays signed off; check it again` : "";
      const mi = res.myinvois, miFilled = mi ? mi.notes.filter(x => x.includes("filled in from MyInvois")).length : 0;
      const einv = mi ? `Kept ${plural(mi.files.reduce((a, f) => a + f.rows, 0), "MyInvois e-Invoice")} (${mi.files.reduce((a, f) => a + f.new, 0)} new, ${mi.files.reduce((a, f) => a + f.changed, 0)} changed); ${plural(miFilled, "SQL document")} filled in` : "";
      if (!p.records.length && (kept.length || mi)) { toast([lines, einv].filter(Boolean).join(". ") + moved + "."); return render(); }
      // Vouchers edited in SQL: one linked to nothing replaced its earlier entry; one linked waits under Changed in SQL.
      const edits = `${res.replaced?.length ? `. Changed in SQL, listed once at the new figure: ${res.replaced.join(", ")}` : ""}${res.changed_linked ? `. ${res.changed_linked} linked ${res.changed_linked === 1 ? "voucher was" : "vouchers were"} changed in SQL: see Changed in SQL` : ""}`;
      toast(`Imported ${res.added} entries; ${res.linked} linked to payments${res.skipped ? `, ${res.skipped} already imported` : ""}${matchedNote(res)}${lines ? `. ${lines}` : ""}${einv ? `. ${einv}` : ""}${edits}${moved}.`);
      return render();
    }
    if (ds.miFilter) { state.miFilter = ds.miFilter; const box = $("#miBox"); if (box) box.innerHTML = myinvoisBox(state.miData); return; }
    if (ds.sqlLines) {
      const row = t.closest("tr"), next = row?.nextElementSibling;
      if (next?.classList.contains("sql-lines-row") && next.dataset.doc === ds.sqlLines) { next.remove(); return; }
      if (next?.classList.contains("sql-lines-row")) next.remove();
      const v = await api(`/api/ledger/doc?entity=${state.entity}&doc_no=${encodeURIComponent(ds.sqlLines)}`);
      const tr = document.createElement("tr");
      tr.className = "sql-lines-row"; tr.dataset.doc = ds.sqlLines;
      tr.innerHTML = `<td colspan="${row.children.length}">${ledgerDocView(v)}</td>`;
      row.after(tr); return;
    }
    if (t.id === "sqlFetch") {
      t.disabled = true; t.textContent = "Reading the folder…";
      try { renderSqlPreview(await api("/api/sql/preview", { json: { entity_id: state.entity, fetch: true } })); }
      finally { t.disabled = false; t.textContent = "Fetch from SQL exports"; }
      return $("#sqlPreview").scrollIntoView({ behavior: "smooth", block: "start" });
    }
    if (ds.sqlTake != null) {  // an export from a company not in Setup: taken only when the owner says whose it is
      if (t.dataset.confirm !== "1") { t.dataset.confirm = "1"; t.textContent = `Click again: "${ds.sqlTake}" is ${ent().code}`; return; }
      await api("/api/sql/take-company", { json: { entity_id: state.entity, company: ds.sqlTake } });
      toast(`Exports printed for "${ds.sqlTake}" are taken for ${ent().code} from now on. Fetching again…`);
      renderSqlPreview(await api("/api/sql/preview", { json: { entity_id: state.entity, fetch: true } }));
      return;
    }
    if (ds.sqlMove) {  // a voucher changed in SQL: its payment's link moves to the new entry only on this click
      const box = t.closest("[data-sql-changed]"), follow = box?.querySelector("[data-sql-follow]")?.checked || false;
      const r = await api(`/api/sql/entries/${ds.sqlMove}/move-link`, { json: { to: +ds.sqlMoveTo, update_amount: follow } });
      toast(`${r.doc_no}: the link of ${r.payment} moved to the amount SQL gives now${r.amount_changed ? ", and the payment's amount changed with it" : "; the payment's amount is as it was"}${matchedNote(r)}`);
      return render();
    }
    if (t.id === "sqlDirSave") {
      const r = await api("/api/settings/sql-exports-dir", { json: { sql_exports_dir: $("#sqlDir").value } });
      state.meta.sql_exports_dir = r.sql_exports_dir; state.meta.sql_exports_default = r.default;
      toast(r.default ? "Reading your Downloads folder" : "Folder saved"); return render();
    }
    if (t.id === "sqlCancel") { state.sqlPreview = null; delete state.sqlPaste[state.entity]; $("#sqlPreview").innerHTML = ""; $("#sqlPaste").value = ""; return; }
    if (t.id === "sqlCreateAll") {
      if (t.dataset.confirm !== "1") { t.dataset.confirm = "1"; t.textContent = "Click again to create them all"; return; }
      const r = await api("/api/sql/entries/create-all", { json: { entity_id: state.entity } });
      toast(`Created ${r.created} payments from SQL${r.linked ? `; ${r.linked} linked to existing payments with the same SQL number` : ""}${r.left ? `; ${r.left} left for you to check (number already linked, changed in SQL?)` : ""}${r.corrections.length ? `; ${r.corrections.length} left out as probably corrections (no money moved)` : ""}; ${r.bank_lines_matched} bank lines matched`); return render();
    }
    if (t.id === "sqlIgnoreAll") {
      if (t.dataset.confirm !== "1") { t.dataset.confirm = "1"; t.textContent = "Click again to ignore them all"; return; }
      const r = await api("/api/sql/entries/ignore", { json: { ids: state.sqlCorrections } });
      toast(r.ignored === 1 ? "1 entry ignored; it is listed under Ignored" : `${r.ignored} entries ignored; they are listed under Ignored`); return render();
    }
    if (t.id === "rematch") {
      const r = await api("/api/statements/rematch", { json: { entity_id: state.entity } });
      toast(`${r.matched} more bank lines matched; ${r.no_docs} marked as bank charges or own transfers`); return render();
    }
    if (ds.sqlCreate) { const r = await api(`/api/sql/entries/${ds.sqlCreate}`, { json: { create_payment: {} } }); toast(`Payment created${matchedNote(r)}`); return render(); }
    if (ds.sqlIgnore) { await api(`/api/sql/entries/${ds.sqlIgnore}`, { json: { status: "ignored" } }); return render(); }
    if (ds.sqlIgnoreIds) {  // every row of a listing entry, so one listed on several rows leaves the list at once
      const r = await api("/api/sql/entries/ignore", { json: { ids: ds.sqlIgnoreIds.split(",").map(Number) } });
      toast(r.ignored === 1 ? "1 entry ignored; it is listed under Ignored" : `${r.ignored} entries ignored; they are listed under Ignored`); return render();
    }
    if (ds.sqlDeletedIds) {  // every row of the listing entry; kept, marked ignored, Un-ignore puts it back
      const r = await api("/api/sql/entries/deleted", { json: { ids: ds.sqlDeletedIds.split(",").map(Number) } });
      toast(`${r.doc_nos.join(", ")} marked as deleted in SQL; listed under Ignored${reconMoved(r)}`); return render();
    }
    if (ds.sqlLinkGo) {
      const v = $(`select[data-sql-link="${ds.sqlLinkGo}"]`).value;
      if (!v) return toast("Choose a payment first.", true);
      const r = await api(`/api/sql/entries/${ds.sqlLinkGo}`, { json: { payment_id: +v } }); toast(`Linked${matchedNote(r)}`); return render();
    }
    if (ds.invSetup) { state.setup.kind = "entities"; return go("setup"); }
    if (ds.invImgUp) return printImage(ds.invImgUp, false);
    if (ds.invImgRemove) return printImage(ds.invImgRemove, true);
    if (ds.sqlNameRemove) return await removeSqlName(t);
    if (ds.sqlUnlink) {
      const r = await api(`/api/sql/entries/${ds.sqlUnlink}/unlink`, { json: {} });
      const list = r.before_tracking ? "Before tracking" : "SQL entries not linked";  // where the SQL page now lists it
      toast(r.kind === "journal" ? `${r.doc_no} unlinked${r.removed ? `, and the payment made from it was removed` : ` from ${r.payment}`}`
        : r.removed ? `${r.doc_no} is back under ${list}, and the payment made from it was removed`
        : `${r.doc_no} unlinked from ${r.payment}; it's back under ${list}`); return render();
    }
    if (ds.sqlUnignore) { const r = await api(`/api/sql/entries/${ds.sqlUnignore}/unignore`, { json: {} }); toast(`${r.doc_no} is back under ${r.kind === "journal" || r.kind === "invoice" ? "Journals and invoices" : r.before_tracking ? "Before tracking" : "SQL entries not linked"}${reconMoved(r)}`); return render(); }
    if (ds.editPayee) { if (!(await mayLeave())) return; return await editPayee(ds.editPayee); }
    if (ds.addMonth) {
      const r = await api(`/api/payees/${ds.addMonth}/add-to-month`, { json: { month: state.month } });
      toast(r.opened ? `${monthName(state.month)} is set up: its checklist and recurring payments were added` : `Added to ${monthName(state.month)}`);
      return render();
    }
    if (t.id === "buildPack") {
      t.disabled = true; t.textContent = "Building…"; $("#packOut").hidden = true;
      let r;
      try { r = await api("/api/audit-pack", { json: { entity_id: state.entity, month: state.month } }); }
      catch (e) {
        // The button works again, and the reason (which document) stays under it after the message goes.
        t.disabled = false; t.textContent = "Build audit pack PDF";
        $("#packOut").textContent = `The pack wasn't built: ${e.message}`; $("#packOut").hidden = false; throw e;
      }
      window.open(r.url, "_blank"); return render();
    }
    if (t.id === "auditorPack") {
      if (!(await ask("The auditor package holds staff pay, bank and ID details. It stays on this PC until you send it. Build it now?", { title: "Build the auditor package?", yes: "Build package", no: "Cancel", tone: "warn", glyph: "pack" }))) return;
      t.disabled = true; t.textContent = "Building…"; $("#packOut").hidden = true;
      try {
        const r = await api("/api/auditor-export", { json: { entity_id: state.entity, month: state.month } });
        // The package also built a fresh audit pack: show it in Recent packs and Before you print, then the link.
        await render();
        $("#packOut").innerHTML = `Auditor package built (${r.files} files${r.left_out ? `, ${r.left_out} left out because they changed or are missing` : ""}): <a href="${r.url}">${esc(r.name)}</a>. It also built a fresh audit pack, and it is in the exports folder on this PC.`;
        $("#packOut").hidden = false; return;
      } catch (e) { $("#packOut").textContent = `The package wasn't built: ${e.message}`; }
      t.disabled = false; t.textContent = "Auditor package"; $("#packOut").hidden = false; return;
    }
    if (t.id === "doBackup" || t.id === "doBackupEnc") {
      const enc = t.id === "doBackupEnc", out = $("#setOut");
      let body = {};
      if (enc) {
        const pw = $("#bkPw").value;
        if (pw.length < 12) return toast("The password needs at least 12 characters.", true);
        if (pw !== $("#bkPw2").value) return toast("The two passwords are not the same.", true);
        body = { password: pw };
      }
      t.disabled = true;
      try {
        const r = await api("/api/backup", { json: body });
        out.textContent = r.warning || `Saved ${r.file}${r.copied ? " and copied to " + r.copied : ""}${r.not_copied ? ". " + r.not_copied : ""}`;
      } catch (e) { out.textContent = e.message; }
      finally { body = null; if ($("#bkPw")) { $("#bkPw").value = ""; $("#bkPw2").value = ""; } t.disabled = false; }
      return;
    }
    if (t.id === "saveBackupDir") {
      const r = await api("/api/settings/backup-dir", { json: { backup_dir: $("#bkDir").value } });
      state.meta.backup_dir = r.backup_dir; toast(r.backup_dir ? "Backup folder saved" : "Backup folder cleared"); return;
    }
    if (t.id === "doCheck") {
      const r = await api("/api/integrity");
      $("#setOut").textContent = r.problems.length ? `${r.problems.length} of ${r.checked} documents are missing or changed: ${r.problems.map(p => p.stored_path).join(", ")}` : `All ${r.checked} documents match their upload fingerprints.`;
    }
  } catch (e) { toast(e.message, true); }
});

document.addEventListener("change", async ev => {
  const t = ev.target;
  try {
    // Only the statements are drawn again, so the account and file chosen for an import stay.
    if (t.dataset.rvSel) { RV().sel[t.dataset.rvSel] = t.checked; return paintBar(); }
    if (t.dataset.invMonth) { state.invMonth = t.value; const box = $("#invPrint"); if (box) box.innerHTML = invoicePrintBar(state.invPrint); return; }
    if (t.dataset.rvKeep) { RV().keep[t.dataset.rvKeep] = t.checked; return; }
    // Move setup: the links save what is chosen.
    if (t.id === "mv-from") { state.setup.move.from = t.value; $("#mvTemplate").href = moveHref("template", t.value ? `&entity=${t.value}` : ""); return; }
    if (t.id === "mv-payees") {
      state.setup.move.payees = t.checked; $("#mv-warn").hidden = !t.checked;
      $("#mvFull").href = moveHref("full", t.checked ? "&payees=1" : ""); return;
    }
    if (t.id === "rvChecked") { RV().checked = t.checked; return; }
    if (t.dataset.rvChoice) {
      const V = RV(), id = +t.dataset.rvChoice;
      V.choice[id] = t.value; if (!t.value) delete V.sel[id];
      document.getElementById(`rv-row-${id}`).outerHTML = rvRow(V.d.lines.find(l => l.id === id));
      return paintBar();
    }
    if (t.dataset.task) {
      // A tick by hand while something is still missing asks first, naming it.
      const task = state.data.tasks.find(x => x.id === +t.dataset.task);
      if (t.checked && task?.lacking.length && !(await ask(`${task.lacking.join(". ")}.`, { title: "Tick anyway?", yes: "Tick anyway", no: "Cancel", tone: "warn", glyph: "checklist", note: "It stays marked Ticked by hand until the missing item is added.", closing: "You can untick it at any time." }))) { t.checked = false; return; }
      await api(`/api/tasks/${t.dataset.task}`, { json: { done: t.checked } }); render();
    }
    if (t.dataset.sqlRow) {
      const r = state.sqlPreview.records.find(x => x.row === +t.dataset.sqlRow); r.payment_id = t.value ? +t.value : null; r.picked = true;
      $("#sqlApply").textContent = applyLabel(state.sqlPreview);
    }
    if (t.id === "sqlJournalPick") {  // the note is worked out again for the journal chosen
      renderSqlPreview(await api("/api/sql/preview", { json: { token: state.sqlPreview.token, journal_id: t.value || null } }));
    }
    if (t.dataset.sqlMap) {
      // The links picked by hand go along, so reading the columns again keeps them for the rows still there.
      const p = state.sqlPreview; const mapping = { ...p.mapping, [t.dataset.sqlMap]: t.value === "" ? null : +t.value };
      const picks = Object.fromEntries(p.records.filter(r => r.picked).map(r => [r.row, r.payment_id]));
      renderSqlPreview(await api("/api/sql/preview", { json: { token: p.token, header_row: p.header_row, mapping, picks } }));
    }
    if (t.dataset.pasteMap) {
      // A column picked by hand: the list is read again with it (nothing saved).
      // The preview goes (Save with it) until the new read comes back; the pickers stay on screen meanwhile.
      const P = state.setup.paste, p = P?.preview || P?.shown;
      if (!p) return;
      const mapping = { ...(p.mapping || {}), [t.dataset.pasteMap]: t.value === "" ? null : +t.value };
      P.shown = { ...p, mapping }; P.preview = null; paintPasteSave(true);  // a second pick while reading keeps this one
      await pasteSave(true, { base: P.shown, header_row: p.header_row ?? null, mapping });
    }
  } catch (e) { toast(e.message, true); }
});

document.addEventListener("submit", async ev => {
  if (ev.target.id === "setupWhy") { ev.preventDefault(); return whySubmit(); }
  const SETUP_SAVES = { setupForm: setupSave, settingsForm: settingsSave, reqForm: () => reqSave(false), chkForm: () => chkSave(false),
    chkCopyForm: () => chkCopySave(false), remForm: () => remSave(false), pasteForm: () => pasteSave(false) };
  if (SETUP_SAVES[ev.target.id]) {
    ev.preventDefault();
    const btn = ev.target.querySelector("button[type=submit]");
    btn.disabled = true;
    try { await SETUP_SAVES[ev.target.id](); } catch (e) { toast(e.message, true); }
    finally { if (btn.isConnected) btn.disabled = false; }
    return;
  }
  if (ev.target.id === "payForm") {
    ev.preventDefault();
    try {
      // Only what was changed, so an untouched estimate stays an estimate
      const now = payFormValues(), changed = {};
      for (const k in now) if (now[k] !== state.payLoaded[k]) changed[k] = now[k];
      if (!Object.keys(changed).length) return toast("Nothing has changed.");
      await api(`/api/payments/${state.openPayment}`, { method: "PATCH", json: changed });
      state.payLoaded = now;  // saved, so the refresh shows what the records now hold
      toast("Saved"); render();
    } catch (e) { toast(e.message, true); }
  }
  if (ev.target.id === "stmtForm") {
    ev.preventDefault();
    const f = $("#stmtFile").files[0];
    if (!f) return toast("Choose the statement PDF first.", true);
    const fd = new FormData(); fd.append("file", f); fd.append("account_id", $("#stmtAcct").value);
    try {
      const r = await api("/api/statements", { form: fd });
      toast(`Imported ${r.lines} lines for ${monthName(r.month)}; ${r.matched} matched, ${r.no_docs} bank charges or own transfers.`);
      Object.assign(state.recon, { rv: null, account: +$("#stmtAcct").value, year: r.month.slice(0, 4), open: r.month });
      render();
    } catch (e) { toast(e.message, true); }
  }
  if (ev.target.id === "openingForm") {
    ev.preventDefault();
    const amount = LT.typedAmount($("#openAmount").value);
    if (!$("#openMonth").value || amount === null) return toast("Choose the month and type the balance as a number.", true);
    try {
      await api("/api/recon/book-opening", { json: { entity_id: state.entity, account_id: state.recon.account, month: $("#openMonth").value, amount } });
      toast("Book opening saved."); drawRecon();
    } catch (e) { toast(e.message, true); }
  }
  if (ev.target.id === "sqlForm") {
    ev.preventDefault();
    const f = $("#sqlFile").files[0];
    if (!f) return toast("Choose the SQL export file first.", true);
    const fd = new FormData(); fd.append("file", f); fd.append("entity_id", state.entity);
    try { renderSqlPreview(await api("/api/sql/preview", { form: fd })); } catch (e) { toast(e.message, true); }
  }
  if (ev.target.id === "sqlPasteForm") {
    ev.preventDefault();
    const text = $("#sqlPaste").value;
    if (!text.trim()) return toast("Paste the rows copied from SQL first.", true);
    try { renderSqlPreview(await api("/api/sql/preview", { json: { entity_id: state.entity, text } })); } catch (e) { toast(e.message, true); }
  }
  if (ev.target.id === "addForm") {
    ev.preventDefault();
    try {
      await api("/api/payments", { json: { entity_id: state.entity, month: state.month, description: $("#ap-desc").value.trim(), category: $("#ap-cat").value,
        amount: $("#ap-amt").value === "" ? null : +$("#ap-amt").value, account_id: +$("#ap-acct").value, due_date: $("#ap-due").value, direction: $("#ap-dir").value } });
      await closeDrawer(); toast("Payment added"); render();
    } catch (e) { toast(e.message, true); }
  }
});

