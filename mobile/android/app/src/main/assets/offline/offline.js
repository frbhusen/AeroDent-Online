(function () {
  "use strict";
  var params = new URLSearchParams(window.location.search);
  var lang = params.get("lang") === "ar" ? "ar" : "en";
  // `currentLanguage` and `t()` come from the web app's i18n.js.
  currentLanguage = lang;
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  document.querySelectorAll("[data-i18n]").forEach(function (node) {
    node.textContent = t(node.getAttribute("data-i18n"));
  });

  // The page to return to is set by the app; the app itself only allows navigating to the
  // configured AeroDent server, whatever this value says.
  var target = params.get("to") || "";
  var retrying = false;
  function retry() {
    if (retrying || !/^https?:\/\//i.test(target)) return;
    retrying = true;
    document.getElementById("retry").disabled = true;
    window.location.replace(target);
  }
  document.getElementById("retry").addEventListener("click", retry);
  window.addEventListener("online", retry);
})();
