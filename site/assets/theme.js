// Runs before the page paints so the chosen theme never flashes.
(function () {
  var root = document.documentElement;
  root.classList.add("js");
  var theme = null;
  try {
    theme = window.localStorage.getItem("jarvis-theme");
  } catch (error) {
    theme = null;
  }
  if (theme !== "light" && theme !== "dark") {
    var light = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches;
    theme = light ? "light" : "dark";
  }
  root.setAttribute("data-theme", theme);
})();
