/* ============================================================================
 * AeroDent Landing Page — Internationalization (i18n)
 * ----------------------------------------------------------------------------
 * ARCHITECTURE
 *   - Arabic (ar) is the ACTIVE, fully-implemented language. Its text lives
 *     directly in the HTML (good for SEO + no flash of untranslated content).
 *   - Every translatable node carries a stable `data-i18n` key. On first run
 *     we snapshot the authored Arabic text for each key, so switching back to
 *     Arabic is always exact.
 *   - English (en) is PREPARED but not yet complete. To ship English later:
 *       1. Fill in the `STRINGS.en` dictionary below (keys already listed).
 *       2. Set `englishEnabled: true` in config.js.
 *     No page rebuild is required — the engine and the switcher are ready.
 *
 * SUPPORTED ATTRIBUTES on elements:
 *   data-i18n="key"            -> replaces textContent
 *   data-i18n-html="key"       -> replaces innerHTML (use only for trusted markup)
 *   data-i18n-attr="attr:key"  -> replaces an attribute (e.g. "placeholder:foo",
 *                                 "aria-label:bar"); multiple separated by ";"
 * ========================================================================== */

(function (global) {
  "use strict";

  // English strings. Fallback = the authored Arabic in the DOM, so partially
  // filling this in never breaks the page. Fill these to enable English.
  var STRINGS = {
    en: {
      // Navigation
      "nav.features": "Features",
      "nav.preview": "Preview",
      "nav.how": "How it works",
      "nav.faq": "FAQ",
      "nav.pricing": "Pricing",
      "pricing.eyebrow": "Pricing",
      "pricing.title": "Simple plans sized to your clinic",
      "pricing.subtitle": "Every plan includes all features and differs only by the number of doctors and secretaries. Try it free for 14 days before you decide.",
      "pricing.popular": "Most popular",
      "pricing.perMonth": "/ month",
      "pricing.allFeatures": "All features included",
      "pricing.cta": "Start your free trial",
      "pricing.contact": "Contact us",
      "pricing.solo.name": "Solo",
      "pricing.solo.who": "For a single dentist",
      "pricing.solo.doctors": "1 doctor",
      "pricing.solo.secretaries": "1 secretary",
      "pricing.clinic.name": "Clinic",
      "pricing.clinic.who": "For small and mid-size clinics",
      "pricing.clinic.doctors": "Up to 3 doctors",
      "pricing.clinic.secretaries": "Up to 3 secretaries",
      "pricing.center.name": "Center",
      "pricing.center.who": "For centers and multiple branches",
      "pricing.center.doctors": "Up to 8 doctors",
      "pricing.center.secretaries": "Up to 8 secretaries",
      "pricing.chain.name": "Clinic group",
      "pricing.chain.who": "For more branches and doctors",
      "pricing.chain.price": "By agreement",
      "pricing.chain.l1": "Custom number of accounts",
      "pricing.chain.l2": "Dedicated support and setup",
      "pricing.note.launch": "Launch offer: the first 10 clinics get 30% off for life.",
      "pricing.note.annual": "Annual billing: pay for 10 months, get 12.",
      "pricing.note.region": "Special pricing by country. No credit card needed for the free trial.",
      "nav.manual": "User manual",
      "nav.cta": "Request a trial",
      "nav.skip": "Skip to main content",
      // Hero
      "hero.eyebrow": "Dental clinic management platform",
      "hero.title": "Run your dental clinic with clarity and confidence",
      "hero.subtitle":
        "AeroDent brings patients, odontogram, treatment plans, appointments, prescriptions, x-rays, invoicing and reports together in one secure, Arabic-first platform.",
      "hero.cta.primary": "Request a 14-day trial",
      "hero.cta.secondary": "View the user manual",
      // Sections (headings)
      "features.title": "Everything your clinic needs, in one place",
      "preview.title": "See AeroDent in action",
      "how.title": "How it works",
      "why.title": "Why AeroDent",
      "audience.title": "Built for",
      "faq.title": "Frequently asked questions",
      "trial.title": "Request your 14-day free trial",
      "footer.rights": "All rights reserved",
      // Form
      "form.username": "Username (English letters, no spaces)",
      "form.usernameHint": "We use it to create your trial login email and password.",
      "form.success.email": "Email",
      "form.success.password": "Password",
      "form.success.note": "Save these details now and change the password in Settings after your first sign-in.",
      "form.success.login": "Sign in to your account",
      "form.name": "Full name",
      "form.clinic": "Clinic name",
      "form.phone": "Phone number",
      "form.location": "Clinic location",
      "form.message": "Message (optional)",
      "form.submit": "Request a 14-day free trial",
      "form.submitting": "Sending…",
    },
  };

  var LANG_KEY = "aerodent_landing_lang";
  var original = null; // snapshot of authored (Arabic) values, keyed by data-i18n key

  function snapshot(root) {
    if (original) return;
    original = { text: {}, html: {}, attr: {} };
    root.querySelectorAll("[data-i18n]").forEach(function (el) {
      original.text[el.getAttribute("data-i18n")] = el.textContent;
    });
    root.querySelectorAll("[data-i18n-html]").forEach(function (el) {
      original.html[el.getAttribute("data-i18n-html")] = el.innerHTML;
    });
    root.querySelectorAll("[data-i18n-attr]").forEach(function (el) {
      el.getAttribute("data-i18n-attr").split(";").forEach(function (pair) {
        var parts = pair.split(":");
        if (parts.length !== 2) return;
        var attr = parts[0].trim();
        var key = parts[1].trim();
        original.attr[key] = { attr: attr, value: el.getAttribute(attr) };
      });
    });
  }

  function apply(lang, root) {
    root = root || document;
    snapshot(root);
    var dict = lang === "ar" ? null : STRINGS[lang] || {};

    function resolve(key, kind) {
      if (lang === "ar") return original[kind][key];
      return dict[key] != null ? dict[key] : original[kind][key];
    }

    root.querySelectorAll("[data-i18n]").forEach(function (el) {
      var v = resolve(el.getAttribute("data-i18n"), "text");
      if (v != null) el.textContent = v;
    });
    root.querySelectorAll("[data-i18n-html]").forEach(function (el) {
      var v = resolve(el.getAttribute("data-i18n-html"), "html");
      if (v != null) el.innerHTML = v;
    });
    root.querySelectorAll("[data-i18n-attr]").forEach(function (el) {
      el.getAttribute("data-i18n-attr").split(";").forEach(function (pair) {
        var parts = pair.split(":");
        if (parts.length !== 2) return;
        var attr = parts[0].trim();
        var key = parts[1].trim();
        var v = lang === "ar"
          ? (original.attr[key] && original.attr[key].value)
          : (dict[key] != null ? dict[key] : (original.attr[key] && original.attr[key].value));
        if (v != null) el.setAttribute(attr, v);
      });
    });

    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  }

  function stored() {
    try {
      return localStorage.getItem(LANG_KEY);
    } catch (e) {
      return null;
    }
  }

  function store(lang) {
    try {
      localStorage.setItem(LANG_KEY, lang);
    } catch (e) {
      /* private mode / blocked storage — ignore, Arabic stays default */
    }
  }

  global.AeroDentI18n = {
    STRINGS: STRINGS,
    apply: apply,
    getStored: stored,
    setStored: store,
    // A language is "available" only if its dictionary exists AND it is enabled.
    isAvailable: function (lang) {
      if (lang === "ar") return true;
      var cfg = global.AERODENT_LANDING_CONFIG || {};
      return lang === "en" ? cfg.englishEnabled === true : false;
    },
  };
})(window);
