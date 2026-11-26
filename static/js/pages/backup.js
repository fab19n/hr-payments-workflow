"use strict";
/* ---------------- Backup ---------------- */
async function viewSettings(main) { return pageDraw("main", page => backupDraw(page, main)); }
async function backupDraw(page, main) {
  const log = await page.read(api("/api/activity"));
  main.innerHTML = `
    <div class="card"><h1>Backup</h1>
      <div class="note">Everything is stored on this PC in <span class="mono">${esc(state.meta.data_dir)}</span>: the database (records.db), uploaded documents and audit packs. Nothing is sent anywhere else.</div>
      <div class="note">Backups are saved in the backups folder on this PC. Encrypted backups are also copied to the backup folder below, if you set one.</div>
      <div class="row"><label class="field" style="flex:1"><span>Backup folder (optional)</span><input id="bkDir" value="${esc(state.meta.backup_dir || "")}" placeholder="C:\\Users\\you\\OneDrive\\HR-Backup" autocomplete="off"></label>
        <button class="ghost" id="saveBackupDir" style="align-self:end">Save folder</button></div>
      <div class="note">If this folder is inside your OneDrive folder, OneDrive uploads it. Only encrypted backups are copied there. Leave it empty to copy nowhere.</div>
      <div class="row"><label class="field"><span>Backup password</span><input type="password" id="bkPw" autocomplete="new-password"></label>
        <label class="field"><span>Type it again</span><input type="password" id="bkPw2" autocomplete="new-password"></label>
        <button class="btn" id="doBackupEnc" style="align-self:end">Make encrypted backup</button></div>
      <div class="note">At least 12 characters. Keep the password safe: without it the backup cannot be opened. Open it with 7-Zip (Windows Explorer cannot open AES zips). Only the contents are protected: file names inside the zip can still be seen.</div>
      <div class="row"><button class="ghost" id="doBackup">Backup on this PC only (not encrypted)</button><button class="ghost" id="doCheck">Check documents haven't changed</button></div>
      <div id="setOut" class="note"></div></div>
    <div class="card"><h2>Activity log</h2><div class="tbl-wrap"><table><tbody>
      ${log.map(a => `<tr><td class="mono muted" style="white-space:nowrap">${esc(a.at.replace("T", " "))}</td><td>${esc(a.what)}</td></tr>`).join("") || `<tr><td class="empty">Nothing yet.</td></tr>`}
    </tbody></table></div></div>`;
}

