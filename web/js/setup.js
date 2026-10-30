// Standalone (desktop) edition only: first-run setup screen and the small UI differences from the
// online edition. Nothing here runs unless window.AERODENT_STANDALONE is true (js/edition.js).

function isStandalone() {
    return Boolean(window.AERODENT_STANDALONE);
}

// The online-only entry points of the sign-in screen do not exist in the desktop edition.
function applyStandaloneChrome() {
    const trialButton = $("#startTrialBtn");
    if (trialButton?.parentElement) trialButton.parentElement.hidden = true;
}

async function standaloneSetupNeeded() {
    try {
        const response = await window.AERODENT_API.get("/api/setup/status");
        return Boolean(response.needed);
    } catch (error) {
        return false;
    }
}

async function showStandaloneSetup() {
    try {
        const response = await window.AERODENT_API.get("/api/setup/countries");
        state.countries = response.data || [];
    } catch (error) {
        state.countries = [];
    }
    document.body.classList.add("online-unauthenticated");
    const screen = $("#setupScreen");
    screen.innerHTML = `
        <form id="setupForm" class="online-login-card setup-card" novalidate>
            <button type="button" class="button button-ghost login-lang-btn" id="setupLangBtn">${currentLanguage === "ar" ? "English" : "العربية"}</button>
            <div class="brand-mark"><img src="icons/icon-192.png" alt="AeroDent"></div>
            <p class="eyebrow">AERODENT</p>
            <h1>${t("setupTitle")}</h1>
            <p class="muted">${t("setupSubtitle")}</p>
            <div class="form-grid">
                <div class="field full-span"><label>${t("setupClinicName")}</label><input name="clinic_name" maxlength="150" required></div>
                <div class="field full-span"><label>${t("setupDoctorName")}</label><input name="doctor_name" maxlength="150" required></div>
                <div class="field full-span"><label>${t("setupEmail")}</label><input name="email" type="email" maxlength="255" dir="ltr" autocomplete="username" required></div>
                <div class="field"><label>${t("password")}</label><input name="password" type="password" minlength="8" autocomplete="new-password" required></div>
                <div class="field"><label>${t("setupConfirmPassword")}</label><input name="confirm" type="password" minlength="8" autocomplete="new-password" required></div>
                ${regionFieldsHtml({ country: "", currency: "SYR" })}
            </div>
            <p id="setupError" class="login-error" role="alert"></p>
            <button id="setupSubmit" class="button button-primary full" type="submit">${t("setupSubmit")}</button>
        </form>`;
    screen.classList.remove("hidden");

    const form = $("#setupForm");
    bindRegionFields(form);
    $("#setupLangBtn").onclick = () => {
        currentLanguage = currentLanguage === "ar" ? "en" : "ar";
        try { localStorage.setItem("aerodent-language", currentLanguage); } catch (_) { /* optional */ }
        setText();
        showStandaloneSetup();
    };
    form.onsubmit = async (event) => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(form));
        const errorNode = $("#setupError");
        errorNode.textContent = "";
        if (data.password !== data.confirm) {
            errorNode.textContent = t("setupPasswordMismatch");
            return;
        }
        const button = $("#setupSubmit");
        button.disabled = true;
        try {
            const response = await window.AERODENT_API.post("/api/setup", {
                clinic_name: data.clinic_name,
                doctor_name: data.doctor_name,
                email: data.email,
                password: data.password,
                country: data.country || null,
                currency: (data.currency || "").trim() || "SYR",
            });
            screen.classList.add("hidden");
            screen.innerHTML = "";
            setOnlineUser(response.user);
            await window.refreshOnlineWorkspace();
        } catch (error) {
            errorNode.textContent = error.message || t("errorOccurred");
            button.disabled = false;
        }
    };
}
