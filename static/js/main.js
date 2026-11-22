"use strict";
// Starts the app: the records' overview, the cycle's months, then the page the address names. If any of it fails (the records can't be read, or a
// reply is not the records) the page says so in its own place, with a Try again that starts again (nothing here needs state.meta to draw).
async function start() {
  try {
    state.meta = await readMeta();
    state.month = currentCycle(); state.day = dayKey();  // the rollover day comes with the settings
    state.entity = firstEntityId();
    paintOrg();
    await openCycleMonths();
    await routerBoot();  // the address in the bar is the place; with none, the Overview
  } catch (e) {
    const main = $("#main");
    main.classList.remove("loading");
    main.innerHTML = errorState({ title: "HR Payments couldn't start", body: "The records couldn't be read just now.", retry: "start", nothingChanged: false });
  }
}
start();
