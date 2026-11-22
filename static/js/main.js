"use strict";
// Starts the app: the records' overview, the cycle's months, then the page the address names. If the records can't be read (or a reply is not the
// records), or the first page can't be drawn, the page says so in its own place, with a Try again that starts again (nothing here needs state.meta
// to draw). A Try again is ignored while a start is running, and a start that a newer one overtook writes nothing. (openCycleMonths says its own
// failures in a toast and carries on.)
async function start() {
  const seq = start.n = (start.n || 0) + 1, mine = () => seq === start.n;
  start.running = true;
  try {
    const meta = await readMeta();
    if (!mine()) return;
    state.meta = meta;
    state.month = currentCycle(); state.day = dayKey();  // the rollover day comes with the settings
    state.entity = firstEntityId();
    paintOrg();
    await openCycleMonths();
    if (!mine()) return;
    await routerBoot();  // the address in the bar is the place; with none, the Overview
  } catch (e) {
    console.error("HR Payments couldn't start:", e);
    if (mine()) {
      const main = $("#main");
      main.classList.remove("loading");
      main.innerHTML = errorState({ title: "HR Payments couldn't start", body: "The records couldn't be read just now.", retry: "start", nothingChanged: false,
        busy: "Starting again…", detail: String(e && e.message || e) });
    }
  } finally { if (mine()) start.running = false; }
}
start();
