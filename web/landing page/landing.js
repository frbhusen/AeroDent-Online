/* ============================================================================
 * AeroDent Landing Page — behaviour
 *   - Mobile nav toggle
 *   - FAQ accordion (accessible)
 *   - Language switcher (Arabic active; English prepared via i18n.js/config.js)
 *   - 14-day trial form: validation + Web3Forms submission
 * No external libraries.
 * ========================================================================== */

(function () {
  "use strict";

  var CFG = window.AERODENT_LANDING_CONFIG || {};
  var I18N = window.AeroDentI18n;

  document.addEventListener("DOMContentLoaded", function () {
    setYear();
    initNav();
    initFaq();
    initLang();
    initTrialForm();
    initAuthCta();
  });

  /* --------------------------------------------------
   * Auth-aware CTA: "تسجيل الدخول" (Login) by default; becomes
   * "لوحة التحكم" (Go to dashboard) when a signed-in session is detected.
   * Same-origin only — when the page is hosted standalone the request fails
   * (no API / cross-origin) and the button correctly stays "Login".
   */
  function initAuthCta() {
    var cta = document.getElementById("authCta");
    if (!cta) return;
    // session-status returns 200 with {active:true|false} whether or not signed in, so it
    // never logs a 401 in the console (unlike /api/auth/me).
    fetch("/api/auth/session-status", { credentials: "include", headers: { Accept: "application/json" } })
      .then(function (res) {
        return res.ok ? res.json() : null;
      })
      .then(function (data) {
        if (data && data.active) {
          cta.textContent = "لوحة التحكم";
          cta.setAttribute("aria-label", "الذهاب إلى لوحة التحكم");
          cta.classList.remove("btn-ghost");
          cta.classList.add("btn-primary");
          cta.href = "/login";
        }
      })
      .catch(function () {
        /* not signed in or cross-origin: keep the default "Login" button */
      });
  }

  /* -------------------------------------------------- footer year */
  function setYear() {
    var y = document.getElementById("year");
    if (y) y.textContent = String(new Date().getFullYear());
  }

  /* -------------------------------------------------- mobile nav */
  function initNav() {
    var toggle = document.getElementById("navToggle");
    var links = document.getElementById("navLinks");
    if (!toggle || !links) return;

    toggle.addEventListener("click", function () {
      var open = links.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });

    // Close the menu after choosing a link (mobile).
    links.addEventListener("click", function (e) {
      if (e.target.closest("a")) {
        links.classList.remove("open");
        toggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  /* -------------------------------------------------- FAQ accordion */
  function initFaq() {
    var list = document.getElementById("faqList");
    if (!list) return;
    list.querySelectorAll(".faq-q").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var expanded = btn.getAttribute("aria-expanded") === "true";
        var panel = btn.nextElementSibling;
        btn.setAttribute("aria-expanded", expanded ? "false" : "true");
        if (expanded) {
          panel.style.maxHeight = null;
        } else {
          panel.style.maxHeight = panel.scrollHeight + "px";
        }
      });
    });
    // Recompute open panel heights on resize (text reflow).
    window.addEventListener("resize", function () {
      list.querySelectorAll('.faq-q[aria-expanded="true"]').forEach(function (btn) {
        var panel = btn.nextElementSibling;
        panel.style.maxHeight = panel.scrollHeight + "px";
      });
    });
  }

  /* -------------------------------------------------- language switch */
  function initLang() {
    var buttons = document.querySelectorAll(".lang-switch button");
    if (!buttons.length || !I18N) return;

    // Apply a stored preference on load (only if that language is available).
    var stored = I18N.getStored();
    if (stored && stored !== "ar" && I18N.isAvailable(stored)) {
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
          return;
        }
        if (!I18N.isAvailable(lang)) {
          // English is prepared but not yet enabled — be honest about it.
          showToast(
            "النسخة الإنجليزية قيد الإعداد وستتوفر قريبًا · English version is coming soon"
          );
          return;
        }
        I18N.apply(lang);
        I18N.setStored(lang);
        setActive(lang);
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

  /* -------------------------------------------------- trial form */
  var MSG = {
    required: "هذا الحقل مطلوب",
    nameShort: "يرجى إدخال الاسم الكامل",
    phoneInvalid: "يرجى إدخال رقم هاتف صحيح",
    clinicShort: "يرجى إدخال اسم العيادة",
    locationShort: "يرجى إدخال موقع العيادة",
    generic: "تعذّر إرسال الطلب. يرجى المحاولة مرة أخرى.",
    network: "تعذّر الاتصال. تحقّق من الإنترنت وحاول مرة أخرى.",
    notConfigured:
      "نموذج الطلب غير مُهيّأ بعد. يرجى التواصل عبر husen_.rajb@outlook.com أو المحاولة لاحقًا.",
  };

  // Phone: 6–20 digits, optional leading +, spaces/()/- allowed. Mirrors backend PHONE_RE.
  var PHONE_RE = /^\+?[0-9 ()\-]{6,30}$/;

  function initTrialForm() {
    var form = document.getElementById("trialForm");
    if (!form) return;

    var submitBtn = document.getElementById("trialSubmit");
    var label = submitBtn.querySelector(".btn-label");
    var formError = document.getElementById("formError");
    var successBox = document.getElementById("trialSuccess");
    var submitting = false;

    // Clear a field's error as the user corrects it.
    form.querySelectorAll("input, textarea").forEach(function (input) {
      input.addEventListener("input", function () {
        clearFieldError(input);
      });
    });

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (submitting) return; // prevent duplicate submissions

      hide(formError);
      var errors = validate(form);
      if (Object.keys(errors).length) {
        showErrors(form, errors);
        focusFirstError(form, errors);
        return;
      }

      // Honeypot filled -> silently treat as success (do not tip off bots).
      if (form.elements.botcheck && form.elements.botcheck.value.trim()) {
        showSuccess();
        return;
      }

      // Not configured yet -> clear, honest message (no silent failure).
      if (!CFG.web3formsAccessKey || CFG.web3formsAccessKey === "WEB3FORMS_ACCESS_KEY_PLACEHOLDER") {
        showFormError(MSG.notConfigured);
        return;
      }

      submitViaWeb3Forms(form);
    });

    function submitViaWeb3Forms(form) {
      setSubmitting(true);

      var lang = document.documentElement.lang || "ar";
      var payload = {
        access_key: CFG.web3formsAccessKey,
        subject: CFG.emailSubject || "AeroDent trial request",
        from_name: "AeroDent Landing Page",
        // Fields (Arabic labels so the delivered email is readable):
        "الاسم الكامل": val(form, "name"),
        "اسم العيادة": val(form, "clinic"),
        "رقم الهاتف": val(form, "phone"),
        "موقع العيادة": val(form, "location"),
        "رسالة": val(form, "message") || "—",
        "اللغة": lang,
        botcheck: "", // Web3Forms native spam field, kept empty for real users
      };

      fetch(CFG.web3formsEndpoint || "https://api.web3forms.com/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      })
        .then(function (res) {
          return res.json().then(function (data) {
            return { ok: res.ok, data: data };
          });
        })
        .then(function (r) {
          if (r.ok && r.data && r.data.success) {
            showSuccess();
          } else {
            setSubmitting(false);
            showFormError((r.data && r.data.message) ? r.data.message : MSG.generic);
          }
        })
        .catch(function () {
          setSubmitting(false);
          showFormError(MSG.network);
        });
    }

    function setSubmitting(on) {
      submitting = on;
      submitBtn.disabled = on;
      if (on) {
        label.dataset.prev = label.textContent;
        label.innerHTML = '<span class="spinner" aria-hidden="true"></span> ' + "جارٍ الإرسال…";
      } else if (label.dataset.prev) {
        label.textContent = label.dataset.prev;
      }
    }

    function showSuccess() {
      form.classList.add("hidden");
      successBox.classList.remove("hidden");
      successBox.focus();
      successBox.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    function showFormError(msg) {
      formError.textContent = msg;
      formError.classList.remove("hidden");
      formError.focus();
    }
  }

  /* ---- validation helpers ---- */
  function validate(form) {
    var errors = {};
    var name = val(form, "name");
    var clinic = val(form, "clinic");
    var phone = val(form, "phone");
    var location = val(form, "location");

    if (!name) errors.name = MSG.required;
    else if (name.length < 2) errors.name = MSG.nameShort;

    if (!clinic) errors.clinic = MSG.required;
    else if (clinic.length < 2) errors.clinic = MSG.clinicShort;

    if (!phone) errors.phone = MSG.required;
    else if (!PHONE_RE.test(phone) || digits(phone) < 6) errors.phone = MSG.phoneInvalid;

    if (!location) errors.location = MSG.required;
    else if (location.length < 2) errors.location = MSG.locationShort;

    return errors;
  }

  function showErrors(form, errors) {
    Object.keys(errors).forEach(function (field) {
      var input = form.elements[field];
      var msg = form.querySelector('[data-error-for="' + field + '"]');
      if (input) input.setAttribute("aria-invalid", "true");
      if (msg) msg.textContent = errors[field];
    });
  }

  function focusFirstError(form, errors) {
    var first = Object.keys(errors)[0];
    if (first && form.elements[first]) form.elements[first].focus();
  }

  function clearFieldError(input) {
    input.removeAttribute("aria-invalid");
    var msg = input.form && input.form.querySelector('[data-error-for="' + input.name + '"]');
    if (msg) msg.textContent = "";
  }

  function val(form, name) {
    var el = form.elements[name];
    return el ? el.value.trim() : "";
  }
  function digits(s) {
    return (s.match(/\d/g) || []).length;
  }
  function hide(el) {
    if (el) el.classList.add("hidden");
  }
})();
