"use strict";
(async function start() {
  state.meta = await api("/api/meta");
  state.month = currentCycle(); state.day = dayKey();  // the rollover day comes with the settings
  state.entity = firstEntityId();
  paintOrg();
  await openCycleMonths();
  renderNav(); render();
})();
