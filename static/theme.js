"use strict";
// Colour theme: Auto (follow Windows) / Light / Dark. Loaded in <head> so the choice is on the page before it is drawn.
// The choice is only a viewer convenience, kept in this browser; the page works without it.
// The three-option control (Auto, Light, Dark) is drawn by the top bar's account menu (core/topbar.js): each option is a button with
// data-theme-set and aria-pressed. A click sets that theme; the control reads the theme now with window.hrpTheme.get().
(function () {
  const ORDER = ["auto", "light", "dark"];
  let now = "auto";  // kept here too, so the choice holds when the browser blocks storage
  try { const v = localStorage.getItem("hrp-theme"); if (ORDER.includes(v)) now = v; } catch (e) {}
  const apply = t => { if (t === "auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.setAttribute("data-theme", t); };
  const paint = t => {
    if (!document.querySelectorAll) return;
    for (const b of document.querySelectorAll("[data-theme-set]")) b.setAttribute("aria-pressed", b.getAttribute("data-theme-set") === t ? "true" : "false");
  };
  apply(now);
  window.hrpTheme = { get: () => now, order: ORDER };
  document.addEventListener("DOMContentLoaded", () => paint(now));
  document.addEventListener("click", ev => {
    const b = ev.target.closest && ev.target.closest("[data-theme-set]");
    if (!b) return;
    const t = b.getAttribute("data-theme-set");
    if (!ORDER.includes(t)) return;
    try { if (t === "auto") localStorage.removeItem("hrp-theme"); else localStorage.setItem("hrp-theme", t); } catch (e) {}
    now = t; apply(t); paint(t);
  });
})();
