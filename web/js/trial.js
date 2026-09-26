// Request-trial page. Served only through the gated /request-trial route (see
// backend/routes/trial.py). Client-side validation mirrors the server's rules for friendly
// feedback; the server remains the authority.
(function () {
    const LANGUAGE_KEY = "aerodent-language";
    const EMAIL_RE = /^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$/;
    const PHONE_RE = /^\+?[0-9 ()\-]{6,30}$/;

    const form = document.getElementById("trialForm");
    const submit = document.getElementById("trialSubmit");
    const formError = document.getElementById("trialFormError");
    const messageInput = document.getElementById("trialMessage");
    const messageCount = document.getElementById("trialMessageCount");

    function readLanguage() {
        try {
            const stored = localStorage.getItem(LANGUAGE_KEY);
            if (stored === "en" || stored === "ar") return stored;
        } catch (_) { /* storage unavailable */ }
        return "ar";
    }

    function applyLanguage() {
        document.documentElement.lang = currentLanguage;
        document.documentElement.dir = currentLanguage === "ar" ? "rtl" : "ltr";
        document.title = `${t("trialTitle")} · AeroDent`;
        document.querySelectorAll("[data-i18n]").forEach((node) => {
            node.textContent = t(node.dataset.i18n);
        });
        document.getElementById("trialLangBtn").textContent = currentLanguage === "ar" ? "English" : "العربية";
        // Re-render any visible errors in the new language.
        document.querySelectorAll(".field-error[data-key]").forEach((node) => {
            node.textContent = t(node.dataset.key);
        });
        if (formError.dataset.key) formError.textContent = t(formError.dataset.key);
    }

    function setFieldError(field, key) {
        const node = form.querySelector(`[data-error-for="${field}"]`);
        const input = form.elements[field];
        if (!node || !input) return;
        if (key) {
            node.dataset.key = key;
            node.textContent = t(key);
            input.setAttribute("aria-invalid", "true");
        } else {
            delete node.dataset.key;
            node.textContent = "";
            input.removeAttribute("aria-invalid");
        }
    }

    function setFormError(key, fallbackText) {
        if (key) {
            formError.dataset.key = key;
            formError.textContent = t(key);
        } else {
            delete formError.dataset.key;
            formError.textContent = fallbackText || "";
        }
    }

    function validate(values) {
        const errors = {};
        if (values.name.length < 2) errors.name = "trialErrorName";
        const digits = (values.phone.match(/[0-9]/g) || []).length;
        if (!PHONE_RE.test(values.phone) || digits < 6) errors.phone = "trialErrorPhone";
        if (!EMAIL_RE.test(values.email)) errors.email = "trialErrorEmail";
        if (values.message.length > 1000) errors.message = "trialErrorMessage";
        return errors;
    }

    function formValues() {
        const data = new FormData(form);
        return {
            name: String(data.get("name") || "").trim(),
            phone: String(data.get("phone") || "").trim(),
            email: String(data.get("email") || "").trim(),
            message: String(data.get("message") || "").trim(),
            website: String(data.get("website") || ""),
        };
    }

    const SERVER_FIELD_KEYS = {
        name: "trialErrorName",
        phone: "trialErrorPhone",
        email: "trialErrorEmail",
        message: "trialErrorMessage",
    };

    form.addEventListener("input", (event) => {
        if (event.target.name && form.querySelector(`[data-error-for="${event.target.name}"]`)?.dataset.key) {
            setFieldError(event.target.name, null);
        }
        if (event.target === messageInput) messageCount.textContent = String(messageInput.value.length);
    });

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        setFormError(null);
        const values = formValues();
        const errors = validate(values);
        ["name", "phone", "email", "message"].forEach((field) => setFieldError(field, errors[field] || null));
        const firstInvalid = ["name", "phone", "email", "message"].find((field) => errors[field]);
        if (firstInvalid) {
            form.elements[firstInvalid].focus();
            return;
        }

        submit.disabled = true;
        submit.classList.add("is-loading");
        try {
            const response = await fetch("/api/trial/requests", {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ ...values, language: currentLanguage }),
            });
            const payload = await response.json().catch(() => ({}));
            if (response.ok) {
                form.classList.add("hidden");
                document.getElementById("trialSuccess").classList.remove("hidden");
                document.querySelector("#trialSuccess a")?.focus();
                return;
            }
            if (response.status === 422 && SERVER_FIELD_KEYS[payload.field]) {
                setFieldError(payload.field, SERVER_FIELD_KEYS[payload.field]);
                form.elements[payload.field]?.focus();
            } else if (response.status === 403) {
                setFormError("trialErrorExpired");
            } else if (response.status === 429) {
                setFormError("trialErrorTooMany");
            } else {
                setFormError("trialErrorGeneric");
            }
        } catch (_) {
            setFormError("trialErrorNetwork");
        } finally {
            submit.disabled = false;
            submit.classList.remove("is-loading");
        }
    });

    document.getElementById("trialLangBtn").addEventListener("click", () => {
        currentLanguage = currentLanguage === "ar" ? "en" : "ar";
        try { localStorage.setItem(LANGUAGE_KEY, currentLanguage); } catch (_) { /* optional */ }
        applyLanguage();
    });

    currentLanguage = readLanguage();
    applyLanguage();
    document.getElementById("trialName").focus();
})();
