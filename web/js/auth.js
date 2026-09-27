async function hashPIN(pin) {
    const encoder = new TextEncoder();
    const data = encoder.encode(pin);

    const hashBuffer = await crypto.subtle.digest("SHA-256", data);

    return Array.from(new Uint8Array(hashBuffer))
        .map((byte) => byte.toString(16).padStart(2, "0"))
        .join("");
}

async function derivePINHash(pin, existingSaltHex) {
    const saltBytes = existingSaltHex
        ? new Uint8Array(existingSaltHex.match(/.{1,2}/g).map((b) => parseInt(b, 16)))
        : crypto.getRandomValues(new Uint8Array(16));

    const keyMaterial = await crypto.subtle.importKey(
        "raw",
        new TextEncoder().encode(pin),
        "PBKDF2",
        false,
        ["deriveBits"],
    );

    const derivedBits = await crypto.subtle.deriveBits(
        { name: "PBKDF2", salt: saltBytes, iterations: 150000, hash: "SHA-256" },
        keyMaterial,
        256,
    );

    const toHex = (bytes) =>
        Array.from(new Uint8Array(bytes)).map((b) => b.toString(16).padStart(2, "0")).join("");

    return { hash: toHex(derivedBits), salt: toHex(saltBytes) };
}

function lockApp() {
    if (window.AERODENT_ONLINE) return;
    const lockScreen = $("#lockScreen");

    if (!lockScreen) {
        console.error("PIN lock screen was not found.");
        return;
    }

    document.querySelector(".app-shell").classList.add("app-locked");

    lockScreen.classList.remove("hidden");

    $("#pinInput").value = "";
    $("#newPINInput").value = "";
    $("#confirmPINInput").value = "";
    $("#pinError").textContent = "";

    $("#unlockSection").classList.remove("hidden");
    $("#setupPINSection").classList.add("hidden");

    $("#lockTitle").textContent = t("lockTitle");

    $("#lockMessage").textContent = t("lockMessage");

    setTimeout(() => {
        $("#pinInput").focus();
    }, 50);
}

function unlockApp() {
    if (window.AERODENT_ONLINE) return;
    document.querySelector(".app-shell").classList.remove("app-locked");

    $("#lockScreen").classList.add("hidden");

    $("#pinInput").value = "";
    $("#pinError").textContent = "";

    resetInactivityTimer();
}

function showPINSetup() {
    if (window.AERODENT_ONLINE) return;
    const lockScreen = $("#lockScreen");

    if (!lockScreen) {
        return;
    }

    // If a PIN already exists, always show the unlock screen.
    if (state.settings.pinHash || state.settings.pinEnabled === true) {
        lockApp();
        return;
    }

    document.querySelector(".app-shell").classList.add("app-locked");

    lockScreen.classList.remove("hidden");

    $("#unlockSection").classList.add("hidden");
    $("#setupPINSection").classList.remove("hidden");

    $("#lockTitle").textContent = t("setupPIN");

    $("#lockMessage").textContent = t("setupPINMessage");

    $("#pinError").textContent = "";

    $("#newPINInput").value = "";
    $("#confirmPINInput").value = "";

    setTimeout(() => {
        $("#newPINInput").focus();
    }, 50);
}

async function savePIN() {
    if (state.settings.pinHash || state.settings.pinEnabled === true) {
        lockApp();
        return;
    }

    const pin = $("#newPINInput").value.trim();

    const confirmPIN = $("#confirmPINInput").value.trim();

    if (!/^\d{4,6}$/.test(pin)) {
        $("#pinError").textContent = t("pinInvalid");

        return;
    }

    if (pin !== confirmPIN) {
        $("#pinError").textContent = t("pinMismatch");

        return;
    }

    const { hash, salt } = await derivePINHash(pin);

    const newSettings = {
        ...state.settings,

        id: 1,

        pinEnabled: true,

        pinHash: hash,

        pinSalt: salt,
    };

    try {
        await dbPut("settings", newSettings);

        state.settings = newSettings;

        $("#pinError").textContent = "";

        unlockApp();

        resetInactivityTimer();
    } catch (error) {
        console.error("Failed to save PIN:", error);

        $("#pinError").textContent =
            t("pinSaveFailed");
    }
}

let failedPinAttempts = 0;
let pinLockUntil = 0;

async function verifyPIN() {
    if (Date.now() < pinLockUntil) {
        const secondsLeft = Math.ceil((pinLockUntil - Date.now()) / 1000);
        $("#pinError").textContent = t("tooManyAttempts").replace("{seconds}", secondsLeft);
        return;
    }

    const pin = $("#pinInput").value.trim();
    if (!pin) {
        $("#pinError").textContent = t("enterPIN");
        return;
    }
    if (!state.settings.pinHash) {
        $("#pinError").textContent = t("noPINConfigured");
        return;
    }

    try {
        const { hash } = await derivePINHash(pin, state.settings.pinSalt);

        if (hash === state.settings.pinHash) {
            failedPinAttempts = 0;
            unlockApp();
            resetInactivityTimer();
        } else {
            failedPinAttempts++;
            if (failedPinAttempts >= 5) {
                pinLockUntil = Date.now() + 30000;
                failedPinAttempts = 0;
            }
            $("#pinError").textContent = t("pinIncorrect");
            $("#pinInput").value = "";
            $("#pinInput").focus();
        }
    } catch (error) {
        console.error("PIN verification failed:", error);
        $("#pinError").textContent = t("pinVerifyFailed");
    }
}

let inactivityTimer = null;

const INACTIVITY_LIMIT = 10 * 60 * 1000;

let lastActivityTime = Date.now();

function resetInactivityTimer() {
    clearTimeout(inactivityTimer);

    if (!state.settings.pinEnabled) {
        return;
    }

    if (
        document
            .querySelector(".app-shell")
            ?.classList.contains("app-locked")
    ) {
        return;
    }

    lastActivityTime = Date.now();

    inactivityTimer = setTimeout(checkInactivity, INACTIVITY_LIMIT);
}

function checkInactivity() {
    if (!state.settings.pinEnabled) {
        return;
    }

    if (
        document
            .querySelector(".app-shell")
            ?.classList.contains("app-locked")
    ) {
        return;
    }

    const inactiveFor =
        Date.now() - lastActivityTime;

    if (inactiveFor >= INACTIVITY_LIMIT) {
        lockApp();
        return;
    }

    inactivityTimer = setTimeout(
        checkInactivity,
        INACTIVITY_LIMIT - inactiveFor
    );
}

function showOnlineLogin() {
    const loginScreen = $("#onlineLoginScreen");
    const appShell = $(".app-shell");
    if (!loginScreen) return;
    loginScreen.classList.remove("hidden");
    appShell?.classList.add("online-auth-hidden");
    $("#onlineEmail")?.focus();
}

function hideOnlineLogin() {
    $("#onlineLoginScreen")?.classList.add("hidden");
    $(".app-shell")?.classList.remove("online-auth-hidden");
}

function clearOnlineClinicState() {
    state.patients = [];
    state.selectedPatient = null;
    state.appointments = [];
    state.treatments = [];
    state.treatmentPlans = [];
    state.invoices = [];
    state.prescriptions = [];
    state.xrays = [];
    state.odontograms = [];
    state.staffList = [];
    state.doctorsList = [];
    state.dashboardData = null;
    state.timelineData = null;
    state.settings = {};
    state.recall = null;
    state.recallError = "";
    state.activeSessions = [];
    state.activeSessionsError = "";
    if (typeof resetInventoryState === "function") resetInventoryState();
}

function setOnlineUser(user) {
    state.auth.authenticated = Boolean(user);
    state.auth.loading = false;
    state.auth.user = user || null;
    document.body.classList.toggle("online-authenticated", Boolean(user));
    document.body.classList.toggle("online-unauthenticated", !user);
    const isSuperAdmin = user?.role === "super_admin";
    document.body.classList.toggle("is-super-admin", isSuperAdmin);
    if (user) {
        if (isSuperAdmin) {
            state.view = "admin_overview";
        }
        state.settings = {
            ...state.settings,
            doctorName: user.name,
            clinicName: user.clinic_id ? `Clinic #${user.clinic_id}` : "AeroDent Platform Admin",
        };
        hideOnlineLogin();
        setText();
        startSessionWatch();
    } else {
        clearOnlineClinicState();
        showOnlineLogin();
    }
}

// Discard every piece of in-memory clinic data by reloading the document. Clearing state
// field by field is fragile (any new module can forget a field); a fresh document cannot leak
// the previous account's patients, dashboard, or permissions into the next session.
function resetOnlineSession(reason) {
    try {
        if (reason) sessionStorage.setItem("aerodent-auth-notice", reason);
    } catch (_) { /* storage unavailable: the notice is optional */ }
    clearOnlineClinicState();
    window.location.replace(`${window.location.pathname}${window.location.search}`);
}

// Checks every minute whether the server-side session is still alive, without counting as
// activity. When the idle/absolute timeout passes (or the session is revoked elsewhere), the
// screen is cleared instead of leaving patient data visible on an unattended workstation.
let sessionWatchTimer = null;

function startSessionWatch() {
    if (!window.AERODENT_ONLINE || sessionWatchTimer) return;
    sessionWatchTimer = setInterval(async () => {
        if (!state.auth.authenticated || document.hidden) return;
        try {
            const status = await window.AERODENT_API.get("/api/auth/session-status");
            if (status && status.active === false) handleOnlineUnauthorized();
        } catch (_) { /* network hiccup: try again next minute */ }
    }, 60 * 1000);
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden && state.auth.authenticated) {
            window.AERODENT_API.get("/api/auth/session-status")
                .then((status) => { if (status && status.active === false) handleOnlineUnauthorized(); })
                .catch(() => {});
        }
    });
}

function handleOnlineUnauthorized() {
    if (!window.AERODENT_ONLINE || !state.auth.authenticated) return;
    state.auth.authenticated = false;
    resetOnlineSession("sessionExpired");
}

window.handleOnlineUnauthorized = handleOnlineUnauthorized;

async function initializeOnlineAuth() {
    state.auth.loading = true;
    try {
        const response = await window.AERODENT_API.get("/api/auth/me");
        setOnlineUser(response.user);
        return true;
    } catch (error) {
        if (error.status === 401) {
            setOnlineUser(null);
            showPendingAuthNotice();
            return false;
        }
        state.auth.loading = false;
        document.body.classList.add("online-unauthenticated");
        showOnlineLogin();
        const errorEl = $("#onlineLoginError");
        if (errorEl) errorEl.textContent = error.message;
        return false;
    }
}

async function loginOnline(event) {
    event.preventDefault();
    const button = $("#onlineLoginButton");
    const errorNode = $("#onlineLoginError");
    const email = $("#onlineEmail").value.trim();
    const password = $("#onlinePassword").value;
    button.disabled = true;
    button.classList.add("is-loading");
    if (errorNode) errorNode.textContent = "";
    try {
        const response = await window.AERODENT_API.post("/api/auth/login", { email, password });
        $("#onlinePassword").value = "";
        setOnlineUser(response.user);
        if (typeof window.refreshOnlineWorkspace === "function") {
            await window.refreshOnlineWorkspace();
        }
    } catch (error) {
        if (errorNode) {
            errorNode.textContent = error.message || "Unable to sign in right now.";
        }
    } finally {
        button.disabled = false;
        button.classList.remove("is-loading");
    }
}

async function logoutOnline() {
    try {
        await window.AERODENT_API.post("/api/auth/logout", {});
    } catch (error) {
        if (error.status !== 401) {
            toast(error.message);
            return;
        }
    }
    state.auth.authenticated = false;
    resetOnlineSession("signedOut");
}

function showPendingAuthNotice() {
    let reason = null;
    try {
        reason = sessionStorage.getItem("aerodent-auth-notice");
        sessionStorage.removeItem("aerodent-auth-notice");
    } catch (_) { /* ignore */ }
    const node = $("#onlineLoginError");
    if (node && reason === "sessionExpired") node.textContent = t("sessionExpiredNotice");
}

function hasRole(...roles) {
    return roles.includes(state.auth.user?.role);
}

function hasPermission(permission) {
    const role = state.auth.user?.role;
    const permissions = {
        super_admin: [
            "admin.read",
            "admin.clinics.read", "admin.clinics.create", "admin.clinics.update", "admin.clinics.delete",
            "admin.users.read", "admin.users.create", "admin.users.update", "admin.users.delete",
            "admin.subscriptions.manage",
        ],
        head_doctor: [
            "dashboard.read",
            "patients.read", "patients.create", "patients.update", "patients.delete",
            "odontogram.read", "odontogram.update",
            "treatments.read", "treatments.create", "treatments.update", "treatments.delete",
            "treatment_plans.read", "treatment_plans.create", "treatment_plans.update", "treatment_plans.delete",
            "appointments.read", "appointments.create", "appointments.update", "appointments.delete",
            "prescriptions.read", "prescriptions.create", "prescriptions.update", "prescriptions.delete",
            "xrays.read", "xrays.create", "xrays.update", "xrays.delete",
            "invoices.read", "invoices.create", "invoices.update", "invoices.delete",
            "clinic_settings.read", "clinic_settings.update",
            "staff.read", "staff.create", "staff.update", "staff.deactivate", "staff.delete",
            "inventory.read", "inventory.create", "inventory.update", "inventory.delete",
            "inventory.stock_in", "inventory.stock_out", "inventory.adjust",
            "inventory.manage_categories", "inventory.manage_suppliers",
        ],
        doctor: [
            "dashboard.read",
            "patients.read", "patients.create", "patients.update", "patients.delete",
            "odontogram.read", "odontogram.update",
            "treatments.read", "treatments.create", "treatments.update", "treatments.delete",
            "treatment_plans.read", "treatment_plans.create", "treatment_plans.update", "treatment_plans.delete",
            "appointments.read", "appointments.create", "appointments.update", "appointments.delete",
            "prescriptions.read", "prescriptions.create", "prescriptions.update", "prescriptions.delete",
            "xrays.read", "xrays.create", "xrays.update", "xrays.delete",
            "invoices.read", "invoices.create", "invoices.update",
            "clinic_settings.read",
            "inventory.read", "inventory.stock_in", "inventory.stock_out",
        ],
        secretary: [
            "dashboard.read",
            "patients.read", "patients.create", "patients.update",
            "odontogram.read",
            "treatments.read",
            "treatment_plans.read",
            "appointments.read", "appointments.create", "appointments.update", "appointments.delete",
            "prescriptions.read",
            "xrays.read",
            "invoices.read", "invoices.create", "invoices.update",
            "inventory.read", "inventory.stock_in", "inventory.stock_out", "inventory.manage_suppliers",
        ],
    };
    return permissions[role]?.includes(permission) || false;
}

// "Ask for a 14-day trial": the server issues a short-lived, HTTP-only intent cookie and the
// request-trial page is only served when that cookie is present (see backend/routes/trial.py).
async function openTrialRequestPage() {
    const button = $("#startTrialBtn");
    const errorNode = $("#onlineLoginError");
    if (button) button.disabled = true;
    try {
        const response = await window.AERODENT_API.post("/api/trial/intent", {});
        window.location.assign(response?.redirect || "/request-trial");
    } catch (error) {
        if (errorNode) errorNode.textContent = error.status === 429 ? t("trialErrorTooMany") : t("trialErrorNetwork");
        if (button) button.disabled = false;
    }
}

function toggleLoginLanguage() {
    currentLanguage = currentLanguage === "ar" ? "en" : "ar";
    storeLanguagePreference(currentLanguage);
    setText();
}

function bindOnlineAuthControls() {
    $("#onlineLoginForm")?.addEventListener("submit", loginOnline);
    $("#onlineLogoutBtn")?.addEventListener("click", logoutOnline);
    $("#startTrialBtn")?.addEventListener("click", openTrialRequestPage);
    $("#loginLangBtn")?.addEventListener("click", toggleLoginLanguage);

    // Password visibility toggle
    const toggleBtn = $("#togglePasswordBtn");
    const pwdInput = $("#onlinePassword");
    if (toggleBtn && pwdInput) {
        toggleBtn.addEventListener("click", () => {
            const isHidden = pwdInput.type === "password";
            pwdInput.type = isHidden ? "text" : "password";
            toggleBtn.textContent = isHidden ? "🙈" : "👁️";
            toggleBtn.setAttribute("aria-label", isHidden ? "Hide password" : "Show password");
        });
    }
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindOnlineAuthControls, { once: true });
} else {
    bindOnlineAuthControls();
}