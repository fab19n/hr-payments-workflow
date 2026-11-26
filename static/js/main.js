"use strict";
// Starts the app: the records' overview, the cycle's months, then the page the address names. If the records can't be read (or a reply is not the
// records), or the first page can't be drawn, the page says so in its own place, with a Try again that starts again (nothing here needs state.meta
// to draw): the stopped page's words when the app can't be reached. A Try again is ignored while a start is running, and a start that a newer one
// overtook writes nothing. (openCycleMonths says its own failures in a toast and carries on.) opts.again: it is that Try again, so a failure
// puts the focus back on the button.
async function start(opts) {
  const seq = start.n = (start.n || 0) + 1, mine = () => seq === start.n;
  start.running = true;
  state.startFailed = false;
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
      state.startFailed = true;  // until a page is drawn, the month's buttons (core/events.js) do nothing
      const main = $("#main"), detail = String(e && e.message || e);
      main.classList.remove("loading");
      main.innerHTML = e && e.network ? stoppedState({ detail, retry: "start" })
        : errorState({ title: "HR Payments couldn't start", body: "The records couldn't be read just now.", retry: "start", nothingChanged: false,
          busy: "Starting again…", detail });
      if (opts?.again) {
        // the button that was pressed is gone with the old card: the focus goes to the new one, unless it has been put somewhere else
        const at = document.activeElement;
        if (!at || at === document.body || at.isConnected === false || main.contains?.(at)) main.querySelector?.('[data-retry="start"]')?.focus?.({ preventScroll: true });
      }
    }
  } finally { if (mine()) start.running = false; }
}
start();
