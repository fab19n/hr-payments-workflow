"use strict";
(async function start() {
  state.meta = await readMeta();
  state.month = currentCycle(); state.day = dayKey();  // the rollover day comes with the settings
  state.entity = firstEntityId();
  paintOrg();
  await openCycleMonths();
  await routerBoot();  // the address in the bar is the place; with none, the Overview
})();
