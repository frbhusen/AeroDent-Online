
let undoAction = null;
let undoTimer = null;

function setText() {
    document.documentElement.lang =
        currentLanguage;

    document.documentElement.dir =
        currentLanguage === "ar"
            ? "rtl"
            : "ltr";

    $$("[data-i18n]").forEach(
        (node) =>
        (node.textContent =
            t(node.dataset.i18n)),
    );

    $$("[data-i18n-placeholder]").forEach(
        (node) =>
        (node.placeholder =
            t(
                node.dataset
                    .i18nPlaceholder
            )),
    );

    const logoutBtn = $("#onlineLogoutBtn");
    if (logoutBtn) {
        logoutBtn.setAttribute("aria-label", t("logout"));
        logoutBtn.title = t("logout");
    }

    $("#langBtn").textContent =
        currentLanguage === "ar"
            ? "English"
            : "العربية";

    const isSuperAdmin = state.auth?.user?.role === "super_admin";
    document.body.classList.toggle("is-super-admin", isSuperAdmin);

    const userName = state.auth?.user?.name || state.settings.doctorName || "Dr. Hussein";
    $("#doctorName").textContent = userName;

    // Show actual clinic name from settings (loaded after login), fallback to Clinic #ID only while loading
    const rawClinicName = state.settings?.clinicName || "";
    const isPlaceholder = !rawClinicName
        || rawClinicName === "------ Dental Clinic"
        || /^Clinic #\d+$/.test(rawClinicName);
    $("#clinicName").textContent = isSuperAdmin
        ? t("superAdminPlatform")
        : (!isPlaceholder ? rawClinicName : (state.auth?.user ? `Clinic #${state.auth.user.clinic_id}` : "")) || t("appName");

    // Dynamic avatar initials
    const avatarEl = $(".avatar");
    if (avatarEl) {
        if (isSuperAdmin) {
            avatarEl.textContent = "SA";
            avatarEl.title = t("superAdminRole");
        } else {
            const parts = userName.trim().split(/\s+/);
            const initials = parts.length > 1
                ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
                : (parts[0].slice(0, 2)).toUpperCase();
            avatarEl.textContent = initials || "DR";
            avatarEl.title = userName;
        }
    }

    // Role badge under clinic name
    let roleBadgeEl = $("#userRoleBadge");
    if (!roleBadgeEl) {
        roleBadgeEl = document.createElement("span");
        roleBadgeEl.id = "userRoleBadge";
        roleBadgeEl.className = "user-role-badge";
        const profileBox = $("#doctorName")?.parentElement;
        if (profileBox) {
            profileBox.appendChild(roleBadgeEl);
        }
    }
    if (roleBadgeEl) {
        const userRole = state.auth?.user?.role;
        if (isSuperAdmin) {
            roleBadgeEl.textContent = `👑 ${t("superAdminRole")}`;
            roleBadgeEl.className = "user-role-badge badge-role-admin";
        } else if (userRole === "head_doctor") {
            roleBadgeEl.textContent = `🩺 ${t("headDoctorRole")}`;
            roleBadgeEl.className = "user-role-badge badge-role-head";
        } else if (userRole === "doctor") {
            roleBadgeEl.textContent = `👨‍⚕️ ${t("doctorRole")}`;
            roleBadgeEl.className = "user-role-badge badge-role-doctor";
        } else if (userRole === "secretary") {
            roleBadgeEl.textContent = `📋 ${t("secretaryRole")}`;
            roleBadgeEl.className = "user-role-badge badge-role-secretary";
        } else {
            roleBadgeEl.textContent = `👨‍⚕️ ${t("doctorRole")}`;
            roleBadgeEl.className = "user-role-badge badge-role-doctor";
        }
    }

    const collapsed =
        document.body.classList.contains(
            "sidebar-collapsed",
        );

    $("#sidebarToggle").setAttribute(
        "aria-label",
        collapsed
            ? t("sidebarExpand")
            : t("sidebarCollapse"),
    );

    $("#sidebarToggle").setAttribute(
        "aria-expanded",
        String(!collapsed),
    );

    // Update status indicator based on online/offline mode
    const statusMode = $("#statusMode");
    if (statusMode) {
        statusMode.textContent = isSuperAdmin
            ? t("superAdminRole")
            : window.AERODENT_ONLINE ? t("savedOnline") : t("savedLocal");
    }
}

function renderNav() {
    const isSuperAdmin = state.auth?.user?.role === "super_admin";
    let navItems;

    if (isSuperAdmin) {
        navItems = SUPER_ADMIN_NAV;
    } else {
        navItems = NAV.filter(([id]) => {
            if (window.AERODENT_ONLINE && id === "settings" && !hasPermission("clinic_settings.read")) {
                return false;
            }
            // Inventory is an online, server-authoritative module; offline mode has no inventory store.
            if (id === "inventory" && (!window.AERODENT_ONLINE || !hasPermission("inventory.read"))) {
                return false;
            }
            return true;
        });
        if (state.auth?.user?.role === "head_doctor") {
            navItems.push(["audit_logs", "📜", "auditLogs"]);
        }
    }

    $("#nav").innerHTML =
        navItems.map(
            ([id, icon, key]) =>
                `<button class="nav-item ${state.view === id
                    ? "active"
                    : ""
                }" data-view="${id}">
                    <span class="nav-icon">
                        ${icon}
                    </span>
                    <span data-i18n="${key}">
                        ${t(key)}
                    </span>
                </button>`,
        ).join("");

    $$(".nav-item").forEach(
        (button) => {
            button.onclick = () => navigateTo(button.dataset.view);
        },
    );
}

// Single source of truth for "which data does this view need". Every navigation path
// (sidebar, dashboard shortcuts, command palette) goes through here so no view is shown stale.
async function loadViewData(view) {
    if (!window.AERODENT_ONLINE) return;
    if (state.auth?.user?.role === "super_admin") {
        if (view === "admin_overview") {
            await loadAdminMetrics();
            await loadAdminClinics();
        } else if (view === "admin_clinics") {
            await loadAdminClinics(state.adminSearch, state.adminStatusFilter);
        } else if (view === "admin_users") {
            await loadAdminClinics();
            await loadAdminUsers(
                state.adminUserClinicFilter !== "all" ? state.adminUserClinicFilter : null,
                state.adminUserRoleFilter,
                state.adminUserSearch,
            );
        } else if (view === "audit_logs" && typeof loadAuditLogs === "function") {
            await loadAuditLogs();
        }
        return;
    }
    if (view === "dashboard") {
        await loadOnlineDashboard();
    } else if (view === "treatments" && state.selectedPatient) {
        state.treatmentPage = 1;
        state.treatmentError = "";
        state.invoicePage = 1;
        state.invoiceError = "";
        await loadOnlineTreatments();
        await loadOnlineInvoices();
    } else if (view === "treatmentPlan" && state.selectedPatient) {
        state.treatmentPlanPage = 1;
        state.treatmentPlanError = "";
        await loadOnlineTreatmentPlans();
    } else if (view === "appointments") {
        await loadOnlineAppointments();
    } else if (view === "prescriptions" && state.selectedPatient) {
        state.prescriptionPage = 1;
        state.prescriptionError = "";
        await loadOnlinePrescriptions();
    } else if (view === "xrays" && state.selectedPatient) {
        state.xrayPage = 1;
        state.xrayError = "";
        await loadOnlineXrays();
    } else if (view === "odontogram" && state.selectedPatient) {
        await loadOnlineOdontogram();
    } else if (view === "settings") {
        if (hasPermission("clinic_settings.read")) await loadOnlineSettings();
        if (hasPermission("staff.read")) await loadOnlineStaff();
    } else if (view === "hr") {
        if (typeof loadOnlineHRData === "function") await loadOnlineHRData();
    } else if (view === "inventory") {
        if (typeof loadInventoryView === "function") await loadInventoryView();
    } else if (view === "audit_logs") {
        if (typeof loadAuditLogs === "function") await loadAuditLogs();
    }
}

async function navigateTo(view) {
    state.view = view;
    await loadViewData(view);
    render();
}

function render() {
    setText();
    renderNav();
    const isSuperAdmin = state.auth?.user?.role === "super_admin";
    const activeNavList = isSuperAdmin ? SUPER_ADMIN_NAV : NAV;
    const section = activeNavList.find((item) => item[0] === state.view)
        || (state.view === "audit_logs" ? ["audit_logs", "📜", "auditLogs"] : null);
    $("#currentSection").textContent = section
        ? t(section[2]).toUpperCase()
        : isSuperAdmin ? "ADMIN" : "OVERVIEW";
    $("#selectedPatientLabel").textContent =
        (isSuperAdmin || state.view === "appointments" || state.view === "dashboard" || state.view === "settings" || state.view === "audit_logs" || state.view === "hr" || state.view === "inventory")
            ? ""
            : state.selectedPatient?.name || t("selectPatient");
    $(".page-heading h1").textContent = section ? t(section[2]) : isSuperAdmin ? t("adminOverview") : t("dashboard");
    const views = {
        dashboard: renderDashboard,
        odontogram: renderOdontogram,
        patients: renderPatients,
        treatments: renderTreatments,
        treatmentPlan: renderTreatmentPlans,
        appointments: renderAppointments,
        prescriptions: renderPrescriptions,
        xrays: renderXrays,
        settings: renderSettings,
        hr: typeof renderHR === "function" ? renderHR : () => "<div>HR</div>",
        inventory: typeof renderInventory === "function" ? renderInventory : () => "<div>Inventory</div>",
        admin_overview: renderAdminOverview,
        admin_clinics: renderAdminClinics,
        admin_users: renderAdminUsers,
        audit_logs: typeof renderAuditLogs === "function" ? renderAuditLogs : () => "<div>Audit Logs</div>",
    };
    const defaultView = isSuperAdmin ? renderAdminOverview : renderDashboard;
    $("#view").innerHTML = (views[state.view] || defaultView)();
    bindView();
}
function modal(title, body) {
    $("#modalContent").innerHTML = `<h2>${title}</h2>${body}`;
    $("#modal").classList.add("show");
}
function toast(message) {
    const node = document.createElement("div");
    node.className = "toast";
    node.textContent = message;
    document.body.append(node);
    setTimeout(() => node.remove(), 2400);
}
function showUndo(message, action) {
    clearTimeout(undoTimer);

    undoAction = action;

    const existingToast = document.querySelector(".undo-toast");

    if (existingToast) {
        existingToast.remove();
    }

    const node = document.createElement("div");

    node.className = "toast undo-toast";

    node.innerHTML = `
        <span>${esc(message)}</span>
        <button type="button" id="undoBtn">
            ${t("undo")}
        </button>
    `;

    document.body.append(node);

    $("#undoBtn").onclick = async () => {
        if (!undoAction) return;

        const actionToRun = undoAction;

        undoAction = null;

        clearTimeout(undoTimer);

        node.remove();

        try {
            await actionToRun();
        } catch (error) {
            console.error("Undo failed:", error);

            toast(
                t("unableUndo")
            );
        }
    };

    undoTimer = setTimeout(() => {
        undoAction = null;
        node.remove();
    }, 5000);
}









