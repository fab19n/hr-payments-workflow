"use strict";
// Colour theme: Auto (follow Windows) / Light / Dark. Loaded in <head> so the choice is on the page before it is drawn.
// The choice is only a viewer convenience, kept in this browser; the page works without it.
(function () {
  const ORDER = ["auto", "light", "dark"], LABEL = { auto: "Auto", light: "Light", dark: "Dark" };
  let now = "auto";  // kept here too, so cycling works when the browser blocks storage
  // storage is read once, at load; after that cycling starts from the value kept here, so a browser that reads but cannot write still reaches Dark
  try { const v = localStorage.getItem("hrp-theme"); if (ORDER.includes(v)) now = v; } catch (e) {}
  const apply = t => { if (t === "auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.setAttribute("data-theme", t); };
  const paint = t => {
    const b = document.getElementById("themeBtn");
    if (b) { b.textContent = "Theme: " + LABEL[t]; b.title = "Colours: Auto follows Windows. Click to change."; }
  };
  apply(now);
  document.addEventListener("DOMContentLoaded", () => paint(now));
  document.addEventListener("click", ev => {
    if (!ev.target.closest || !ev.target.closest("#themeBtn")) return;
    const t = ORDER[(ORDER.indexOf(now) + 1) % ORDER.length];
    try { if (t === "auto") localStorage.removeItem("hrp-theme"); else localStorage.setItem("hrp-theme", t); } catch (e) {}
    now = t; apply(t); paint(t);
  });
})();
