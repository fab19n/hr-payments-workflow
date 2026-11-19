"use strict";
/* ---------------- Balances kept in this browser before slice 8 ----------------
   Until slice 8 the Budget page kept a month's bank balance and its date in this browser (bal-<company id>-<month> and
   asat-<company id>-<month>). The stored budget is the one place for them now. The first time a month's stored budget is
   opened, a balance or date it doesn't have yet goes across from the browser once, and the browser's copy is removed. A month
   not set up keeps them until its budget is set up. Every storage access may fail (a private window, storage turned off):
   nothing is moved then, and the page works as before. */
function legacyGet(k) { try { return localStorage.getItem(k) || ""; } catch { return ""; } }
function legacyDrop(k) { try { localStorage.removeItem(k); } catch { /* not kept */ } }

// Resolves true when something was moved to the stored budget (the page then reads it again).
async function carryBrowserBalance(d) {
  if (!d || !d.stored) return false;  // no stored budget yet: the browser's copy stays until it is set up
  const eid = d.entity.id, balKey = `bal-${eid}-${d.month}`, dateKey = `asat-${eid}-${d.month}`;
  const bal = legacyGet(balKey).trim(), when = legacyGet(dateKey).trim();
  if (!bal && !when) return false;
  const move = {};
  const n = bal.replace(/,/g, "");
  if (d.balance == null && n !== "" && Number.isFinite(+n)) move.balance = +n;
  // The date as it was kept, if it is a real day; never today in its place (the page then asks for the date).
  if (!d.saved_as_at && /^[2-9]\d{3}-\d{2}-\d{2}$/.test(when) && !isNaN(new Date(when))) move.as_at = when;
  try {
    if (Object.keys(move).length) await api("/api/budget/header", { json: { entity_id: eid, month: d.month, ...move } });
  } catch { return false; }  // not taken: the browser's copy stays for next time
  legacyDrop(balKey); legacyDrop(dateKey);
  return Object.keys(move).length > 0;
}
