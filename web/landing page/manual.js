/* ============================================================================
 * AeroDent User Manual — behaviour
 *   - Footer year
 *   - Mobile nav toggle + collapsible TOC
 *   - TOC scrollspy (highlights the current section)
 *   - Language switch (shared with landing: Arabic active, English prepared)
 * ========================================================================== */

(function () {
  "use strict";

  var I18N = window.AeroDentI18n;

  document.addEventListener("DOMContentLoaded", function () {
    var y = document.getElementById("year");
    if (y) y.textContent = String(new Date().getFullYear());

    initNav();
    initTocToggle();
    initScrollSpy();
    initLang();
  });

  function initNav() {
    var toggle = document.getElementById("navToggle");
    var links = document.getElementById("navLinks");
    if (!toggle || !links) return;
    toggle.addEventListener("click", function () {
      var open = links.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  function initTocToggle() {
    var toc = document.getElementById("toc");
    var btn = document.getElementById("tocToggle");
    var list = document.getElementById("tocList");
    if (!toc || !btn) return;
    btn.addEventListener("click", function () {
      var open = toc.classList.toggle("open");
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    });
    // On small screens, collapse the TOC after picking a section.
    if (list) {
      list.addEventListener("click", function (e) {
        if (e.target.closest("a") && window.matchMedia("(max-width: 900px)").matches) {
          toc.classList.remove("open");
          btn.setAttribute("aria-expanded", "false");
        }
      });
    }
  }

  function initScrollSpy() {
    var links = Array.prototype.slice.call(
      document.querySelectorAll("#tocList a")
    );
    if (!links.length || !("IntersectionObserver" in window)) return;

    var byId = {};
    links.forEach(function (a) {
      var id = a.getAttribute("href").slice(1);
      byId[id] = a;
    });

    var current = null;
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            if (current) current.classList.remove("active");
            var a = byId[entry.target.id];
            if (a) {
              a.classList.add("active");
              current = a;
            }
          }
        });
      },
      { rootMargin: "-20% 0px -70% 0px", threshold: 0 }
    );

    Object.keys(byId).forEach(function (id) {
      var section = document.getElementById(id);
      if (section) observer.observe(section);
    });
  }

  /* Language switch — identical behaviour/contract to the landing page. */
  function initLang() {
    var buttons = document.querySelectorAll(".lang-switch button");
    if (!buttons.length || !I18N) return;

    var stored = I18N.getStored();
    if (stored && stored !== "ar" && I18N.isAvailable(stored)) {
      I18N.apply(stored);
      setActive(stored);
    } else {
      I18N.apply("ar");
      setActive("ar");
    }

    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var lang = btn.getAttribute("data-lang");
        if (lang === "ar") {
          I18N.apply("ar");
          I18N.setStored("ar");
          setActive("ar");
        } else if (I18N.isAvailable(lang)) {
          I18N.apply(lang);
          I18N.setStored(lang);
          setActive(lang);
        } else {
          showToast("النسخة الإنجليزية قيد الإعداد وستتوفر قريبًا · English version is coming soon");
        }
      });
    });

    function setActive(lang) {
      buttons.forEach(function (b) {
        b.setAttribute("aria-pressed", b.getAttribute("data-lang") === lang ? "true" : "false");
      });
    }
  }

  var toastTimer = null;
  function showToast(msg) {
    var el = document.getElementById("toast");
    if (!el) return;
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      el.classList.remove("show");
    }, 4000);
  }
})();
