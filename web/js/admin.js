// ==========================================
// AeroDent Super Admin Management System
// Platform Subscriptions & Clinic Control
// ==========================================

async function loadAdminMetrics() {
    if (!window.AERODENT_ONLINE || state.auth?.user?.role !== "super_admin") return;
    try {
        const res = await window.AERODENT_API.get("/api/admin/metrics");
        state.adminMetrics = res.data;
    } catch (err) {
        console.error("Failed to load admin metrics:", err);
    }
}

async function loadAdminClinics(search = "", status = "all") {
    if (!window.AERODENT_ONLINE || state.auth?.user?.role !== "super_admin") return;
    state.adminLoading = true;
    try {
        const params = new URLSearchParams();
        if (search) params.append("search", search);
        if (status && status !== "all") params.append("status", status);
        const query = params.toString() ? `?${params.toString()}` : "";
        const res = await window.AERODENT_API.get(`/api/admin/clinics${query}`);
        state.adminClinics = res.data || [];
    } catch (err) {
        toast(err.message || "Failed to load clinics");
    } finally {
        state.adminLoading = false;
    }
}

async function loadAdminUsers(clinicId = null, role = "", search = "") {
    if (!window.AERODENT_ONLINE || state.auth?.user?.role !== "super_admin") return;
    state.adminLoading = true;
    try {
        const params = new URLSearchParams();
        if (clinicId) params.append("clinic_id", clinicId);
        if (role && role !== "all") params.append("role", role);
        if (search) params.append("search", search);
        const query = params.toString() ? `?${params.toString()}` : "";
        const res = await window.AERODENT_API.get(`/api/admin/users${query}`);
        state.adminUsers = res.data || [];
    } catch (err) {
        toast(err.message || "Failed to load users");
    } finally {
        state.adminLoading = false;
    }
}

function _formatExpiration(expiresAtStr) {
    if (!expiresAtStr) return `<span class="muted">${t("noExpiration")}</span>`;
    const exp = new Date(expiresAtStr);
    const now = new Date();
    const diffDays = Math.round((exp - now) / (1000 * 60 * 60 * 24));

    const dateFormatted = exp.toLocaleDateString(currentLanguage === "ar" ? "ar-SA" : "en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
    });

    if (diffDays < 0) {
        return `<span class="admin-status-pill status-danger" title="${dateFormatted}"><span class="dot"></span>${t("expiredDaysAgo").replace("{days}", Math.abs(diffDays))}</span>`;
    }
    if (diffDays <= 7) {
        return `<span class="admin-status-pill status-warning" title="${dateFormatted}"><span class="dot"></span>${diffDays} ${t("daysRemaining")}</span>`;
    }
    return `<span class="admin-status-pill status-active" title="${dateFormatted}"><span class="dot"></span>${diffDays} ${t("daysRemaining")}</span>`;
}

function _statusBadge(effectiveStatus, subStatus, isActive) {
    if (!isActive) {
        return `<span class="admin-status-pill status-neutral"><span class="dot"></span>${t("filterInactive")}</span>`;
    }
    if (effectiveStatus === "head_doctor_inactive") {
        return `<span class="admin-status-pill status-warning" title="${t("cascadeDeactivateWarning")}"><span class="dot"></span>${t("filterHeadInactive")}</span>`;
    }
    if (effectiveStatus === "subscription_expired") {
        return `<span class="admin-status-pill status-danger"><span class="dot"></span>${t("filterExpired")}</span>`;
    }
    if (subStatus === "suspended" || subStatus === "cancelled") {
        return `<span class="admin-status-pill status-neutral"><span class="dot"></span>${t("filterSuspended")}</span>`;
    }
    if (subStatus === "trial") {
        return `<span class="admin-status-pill status-trial"><span class="dot"></span>Trial</span>`;
    }
    return `<span class="admin-status-pill status-active"><span class="dot"></span>${t("filterActive")}</span>`;
}

// ------------------------------------------
// View 1: Super Admin Overview
// ------------------------------------------
function renderAdminOverview() {
    const m = state.adminMetrics || {};
    const totalClinics = m.total_clinics ?? 0;
    const activeClinics = m.active_clinics ?? 0;
    const activeSubs = m.active_subscriptions ?? 0;
    const expiredSubs = m.expired_subscriptions ?? 0;
    const totalStaff = m.total_users ?? 0;
    const headDocs = m.total_head_doctors ?? 0;
    const regularDocs = m.total_doctors ?? 0;
    const secretaries = m.total_secretaries ?? 0;

    const clinics = state.adminClinics || [];
    const attentionCount = clinics.filter(c => c.effective_status === "subscription_expired" || c.effective_status === "head_doctor_inactive" || !c.is_active).length;
    const recentClinics = clinics.slice(0, 8);

    const clinicRows = recentClinics.map((c) => {
        const headDoc = c.head_doctors?.[0] || { name: t("none"), email: "-" };
        return `
            <tr>
                <td>
                    <div style="font-weight:600;color:#0f172a;">${esc(c.name)} <span class="badge badge-gray" style="font-weight:normal;font-size:10px;">ID: ${c.id}</span></div>
                    <small class="muted">${esc(c.phone || "")} ${c.address ? "· " + esc(c.address) : ""}</small>
                </td>
                <td>
                    <div style="font-weight:500;">${esc(headDoc.name)}</div>
                    <small class="muted">${esc(headDoc.email)}</small>
                </td>
                <td>${_statusBadge(c.effective_status, c.subscription_status, c.is_active)}</td>
                <td>${_formatExpiration(c.subscription_expires_at)}</td>
                <td style="text-align:end;">
                    <div class="admin-action-group">
                        <button class="btn-admin-action" data-admin-extend-clinic="${c.id}" data-days="30" title="${t("quickExtend30")}">+30d</button>
                        <button class="btn-admin-action btn-admin-primary" data-admin-manage-clinic="${c.id}">${t("extendSubscription")}</button>
                        <button class="btn-admin-action btn-admin-danger btn-admin-icon" data-admin-delete-clinic="${c.id}" title="${t("deleteClinic")}">🗑️</button>
                    </div>
                </td>
            </tr>
        `;
    }).join("");

    const adminUserName = state.auth?.user?.name || "Platform Admin";
    const todayStr = new Date().toLocaleDateString(currentLanguage === "ar" ? "ar-SA" : "en-US", {
        weekday: "long",
        year: "numeric",
        month: "long",
        day: "numeric",
    });

    return `
        <div class="admin-container">
            <div class="dashboard-welcome-banner" style="background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:16px 22px;margin-bottom:20px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;box-shadow:0 2px 6px -1px rgba(0,0,0,0.04);">
                <div style="display:flex;align-items:center;gap:14px;">
                    <div style="width:48px;height:48px;border-radius:12px;background:#faf5ff;border:1px solid #d8b4fe;display:flex;align-items:center;justify-content:center;font-size:24px;">
                        👑
                    </div>
                    <div>
                        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
                            <h2 style="margin:0;font-size:18px;font-weight:700;color:#0f172a;">${esc(adminUserName)}</h2>
                            <span class="user-role-badge badge-role-admin" style="font-size:12px;padding:4px 12px;margin-top:0;display:inline-flex;align-items:center;gap:4px;">
                                <span>👑</span>
                                <span>${t("superAdminRole") || "Super Admin"}</span>
                            </span>
                        </div>
                        <p class="muted" style="margin:3px 0 0 0;font-size:13px;display:flex;align-items:center;gap:6px;">
                            <span>🌐</span>
                            <span>${t("superAdminPlatform") || "AeroDent Platform Admin"}</span>
                        </p>
                    </div>
                </div>
                <div style="text-align:${currentLanguage === "ar" ? "left" : "right"};">
                    <div style="font-size:13px;font-weight:600;color:#334155;">${t("today")}</div>
                    <div class="muted" style="font-size:12px;">${todayStr}</div>
                </div>
            </div>

            <div class="admin-stats-grid">
                <div class="admin-stat-card" style="--stat-accent:#0369a1;--stat-bg:#f0f9ff;">
                    <div class="admin-stat-icon">🏥</div>
                    <div class="admin-stat-info">
                        <span class="admin-stat-title">${t("totalClinics")}</span>
                        <span class="admin-stat-value">${totalClinics}</span>
                        <span class="admin-stat-sub">${activeClinics} ${t("filterActive")}</span>
                    </div>
                </div>
                <div class="admin-stat-card" style="--stat-accent:#16a34a;--stat-bg:#f0fdf4;">
                    <div class="admin-stat-icon">✨</div>
                    <div class="admin-stat-info">
                        <span class="admin-stat-title">${t("activeSubscriptions")}</span>
                        <span class="admin-stat-value" style="color:#16a34a;">${activeSubs}</span>
                        <span class="admin-stat-sub">${expiredSubs} ${t("filterExpired")}</span>
                    </div>
                </div>
                <div class="admin-stat-card" style="--stat-accent:#ea580c;--stat-bg:#fff7ed;">
                    <div class="admin-stat-icon">⚠️</div>
                    <div class="admin-stat-info">
                        <span class="admin-stat-title">${t("attentionNeeded")}</span>
                        <span class="admin-stat-value" style="color:#ea580c;">${attentionCount}</span>
                        <span class="admin-stat-sub">${expiredSubs} ${t("filterExpired")} · ${m.inactive_clinics ?? 0} ${t("filterInactive")}</span>
                    </div>
                </div>
                <div class="admin-stat-card" style="--stat-accent:#7c3aed;--stat-bg:#faf5ff;">
                    <div class="admin-stat-icon">👥</div>
                    <div class="admin-stat-info">
                        <span class="admin-stat-title">${t("totalStaff")}</span>
                        <span class="admin-stat-value">${totalStaff}</span>
                        <span class="admin-stat-sub">${headDocs} ${t("headDoctorRole")} · ${regularDocs} ${t("doctorRole")}</span>
                    </div>
                </div>
            </div>

            <div class="admin-card">
                <div class="admin-card-header">
                    <div>
                        <h2>${t("adminClinics")}</h2>
                        <p>${t("superAdminTagline")}</p>
                    </div>
                    <div style="display:flex;gap:8px;">
                        <button class="button button-primary" data-action="adminCreateClinic">＋ ${t("createClinic")}</button>
                        <button class="btn-admin-action" data-view="admin_clinics">${t("viewAll") || "View All"}</button>
                    </div>
                </div>

                <div class="admin-table-wrapper">
                    <table class="admin-table">
                        <thead>
                            <tr>
                                <th>${t("clinicNameLabel")}</th>
                                <th>${t("headDoctorRole")}</th>
                                <th>${t("subscriptionStatus")}</th>
                                <th>${t("subscriptionExpires")}</th>
                                <th style="text-align:end;">${t("actions")}</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${clinicRows || `<tr><td colspan="5" style="text-align:center;padding:32px;" class="muted">${t("noClinicsFound")}</td></tr>`}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
}

// ------------------------------------------
// View 2: Clinics & Subscriptions Control
// ------------------------------------------
function renderAdminClinics() {
    const clinics = state.adminClinics || [];
    const searchVal = state.adminSearch || "";
    const filterVal = state.adminStatusFilter || "all";

    const allCount = clinics.length;
    const activeCount = clinics.filter(c => c.effective_status === "active").length;
    const expiredCount = clinics.filter(c => c.effective_status === "subscription_expired").length;
    const headInactiveCount = clinics.filter(c => c.effective_status === "head_doctor_inactive").length;
    const inactiveCount = clinics.filter(c => !c.is_active).length;

    const rows = clinics.map((c) => {
        const headDoc = c.head_doctors?.[0] || { name: t("none"), email: "-", is_active: false };
        const staffSummary = `${c.staff_summary?.doctors ?? 0} ${t("doctorRole")} · ${c.staff_summary?.secretaries ?? 0} ${t("secretaryRole")}`;
        const isActive = c.is_active;

        return `
            <tr>
                <td>
                    <div style="font-weight:600;color:#0f172a;">${esc(c.name)} <span class="badge badge-gray" style="font-weight:normal;font-size:10px;">ID: ${c.id}</span></div>
                    <small class="muted">${esc(c.phone || "")} ${c.address ? "· " + esc(c.address) : ""}</small>
                </td>
                <td>
                    <div style="font-weight:500;">
                        ${esc(headDoc.name)}
                        ${headDoc.is_active ? `<span class="admin-status-pill status-active" style="padding:1px 6px;font-size:10px;"><span class="dot"></span>${t("filterActive")}</span>` : `<span class="admin-status-pill status-warning" style="padding:1px 6px;font-size:10px;" title="${t("cascadeDeactivateWarning")}"><span class="dot"></span>${t("filterInactive")}</span>`}
                    </div>
                    <small class="muted">${esc(headDoc.email)}</small>
                </td>
                <td><small style="color:#475569;font-weight:500;">${staffSummary}</small></td>
                <td>${_statusBadge(c.effective_status, c.subscription_status, c.is_active)}</td>
                <td>${_formatExpiration(c.subscription_expires_at)}</td>
                <td>
                    <button class="btn-admin-action ${isActive ? "" : "btn-admin-primary"}" data-admin-toggle-clinic="${c.id}" data-active="${isActive}">
                        ${isActive ? t("deactivate") : t("activate")}
                    </button>
                </td>
                <td style="text-align:end;">
                    <div class="admin-action-group">
                        <button class="btn-admin-action" data-admin-extend-clinic="${c.id}" data-days="30" title="${t("quickExtend30")}">+30d</button>
                        <button class="btn-admin-action btn-admin-primary" data-admin-manage-clinic="${c.id}" title="${t("extendSubscription")}">💳 ${t("manageClinic")}</button>
                        <button class="btn-admin-action" data-admin-edit-clinic="${c.id}" title="${t("edit")}">✎</button>
                        <button class="btn-admin-action btn-admin-danger btn-admin-icon" data-admin-delete-clinic="${c.id}" title="${t("deleteClinic")}">🗑️</button>
                    </div>
                </td>
            </tr>
        `;
    }).join("");

    return `
        <div class="admin-container">
            <div class="admin-card">
                <div class="admin-card-header">
                    <div>
                        <h2>${t("adminClinics")}</h2>
                        <p>${t("superAdminTagline")}</p>
                    </div>
                    <button class="button button-primary" data-action="adminCreateClinic">＋ ${t("createClinic")}</button>
                </div>

                <div class="admin-toolbar">
                    <div class="admin-filter-group">
                        <button type="button" class="admin-filter-chip ${filterVal === "all" ? "active" : ""}" data-filter-status="all">
                            ${t("filterAll")} <span class="chip-count">${allCount}</span>
                        </button>
                        <button type="button" class="admin-filter-chip ${filterVal === "active" ? "active" : ""}" data-filter-status="active">
                            ${t("filterActive")} <span class="chip-count">${activeCount}</span>
                        </button>
                        <button type="button" class="admin-filter-chip ${filterVal === "expired" ? "active" : ""}" data-filter-status="expired">
                            ${t("filterExpired")} <span class="chip-count">${expiredCount}</span>
                        </button>
                        <button type="button" class="admin-filter-chip ${filterVal === "head_doctor_inactive" ? "active" : ""}" data-filter-status="head_doctor_inactive">
                            ${t("filterHeadInactive")} <span class="chip-count">${headInactiveCount}</span>
                        </button>
                        <button type="button" class="admin-filter-chip ${filterVal === "inactive" ? "active" : ""}" data-filter-status="inactive">
                            ${t("filterInactive")} <span class="chip-count">${inactiveCount}</span>
                        </button>
                    </div>

                    <div class="admin-search-box">
                        <span style="color:#94a3b8;margin-right:6px;font-size:13px;">🔍</span>
                        <input type="text" id="adminClinicSearch" placeholder="${t("adminSearchClinics")}" value="${esc(searchVal)}">
                    </div>
                </div>

                <div class="admin-table-wrapper">
                    <table class="admin-table">
                        <thead>
                            <tr>
                                <th>${t("clinicNameLabel")}</th>
                                <th>${t("headDoctorRole")}</th>
                                <th>${t("totalStaff")}</th>
                                <th>${t("subscriptionStatus")}</th>
                                <th>${t("subscriptionExpires")}</th>
                                <th>${t("toggleClinicActive")}</th>
                                <th style="text-align:end;">${t("actions")}</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${rows || `<tr><td colspan="7" style="text-align:center;padding:32px;" class="muted">${t("noClinicsFound")}</td></tr>`}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
}

// ------------------------------------------
// View 3: Global Users Management
// ------------------------------------------
function renderAdminUsers() {
    const users = state.adminUsers || [];
    const clinics = state.adminClinics || [];
    const searchVal = state.adminUserSearch || "";
    const roleVal = state.adminUserRoleFilter || "all";
    const clinicVal = state.adminUserClinicFilter || "all";

    const rows = users.map((u) => {
        const isSelf = u.id === state.auth?.user?.id;
        const isHead = u.role === "head_doctor";
        const roleLabel = u.role === "super_admin" ? t("superAdminRole") : u.role === "head_doctor" ? t("headDoctorRole") : u.role === "doctor" ? t("doctorRole") : t("secretaryRole");
        const roleBadge = u.role === "super_admin" ? "badge-purple" : u.role === "head_doctor" ? "badge-blue" : "badge-gray";

        return `
            <tr>
                <td>
                    <div style="font-weight:600;color:#0f172a;">${esc(u.name)}</div>
                    <small class="muted">${esc(u.email)}</small>
                </td>
                <td><b>${esc(u.clinic_name)}</b></td>
                <td><span class="badge ${roleBadge}">${roleLabel}</span></td>
                <td>
                    ${u.is_active ? `<span class="admin-status-pill status-active"><span class="dot"></span>${t("filterActive")}</span>` : `<span class="admin-status-pill status-neutral"><span class="dot"></span>${t("filterInactive")}</span>`}
                </td>
                <td>
                    ${!isSelf ? `
                        <button class="btn-admin-action ${u.is_active ? "" : "btn-admin-primary"}" data-admin-toggle-user="${u.id}" data-role="${u.role}" data-active="${u.is_active}" title="${isHead ? t("cascadeDeactivateWarning") : ""}">
                            ${u.is_active ? t("deactivate") : t("activate")}
                        </button>
                    ` : `<small class="muted">(You)</small>`}
                </td>
                <td style="text-align:end;">
                    <div class="admin-action-group">
                        <button class="btn-admin-action" data-admin-edit-user="${u.id}">✎ ${t("edit")}</button>
                        ${!isSelf ? `<button class="btn-admin-action btn-admin-danger btn-admin-icon" data-admin-delete-user="${u.id}" title="${t("deleteStaff") || "Delete"}">🗑️</button>` : ""}
                    </div>
                </td>
            </tr>
        `;
    }).join("");

    const clinicOptions = clinics.map((c) => `<option value="${c.id}" ${String(clinicVal) === String(c.id) ? "selected" : ""}>${esc(c.name)}</option>`).join("");

    return `
        <div class="admin-container">
            <div class="admin-card">
                <div class="admin-card-header">
                    <div>
                        <h2>${t("adminUsers")}</h2>
                        <p>${t("superAdminTagline")}</p>
                    </div>
                    <button class="button button-primary" data-action="adminCreateUser">＋ ${t("createUser")}</button>
                </div>

                <div class="admin-toolbar">
                    <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
                        <div class="admin-search-box">
                            <span style="color:#94a3b8;margin-right:6px;font-size:13px;">🔍</span>
                            <input type="text" id="adminUserSearch" placeholder="${t("adminSearchUsers")}" value="${esc(searchVal)}">
                        </div>
                        <select id="adminUserRoleFilter" style="max-width:180px;height:38px;padding:0 10px;border-radius:9px;border:1px solid #cbd5e1;">
                            <option value="all" ${roleVal === "all" ? "selected" : ""}>${t("filterAll")} (${t("assignRole")})</option>
                            <option value="head_doctor" ${roleVal === "head_doctor" ? "selected" : ""}>${t("headDoctorRole")}</option>
                            <option value="doctor" ${roleVal === "doctor" ? "selected" : ""}>${t("doctorRole")}</option>
                            <option value="secretary" ${roleVal === "secretary" ? "selected" : ""}>${t("secretaryRole")}</option>
                            <option value="super_admin" ${roleVal === "super_admin" ? "selected" : ""}>${t("superAdminRole")}</option>
                        </select>
                        <select id="adminUserClinicFilter" style="max-width:200px;height:38px;padding:0 10px;border-radius:9px;border:1px solid #cbd5e1;">
                            <option value="all" ${clinicVal === "all" ? "selected" : ""}>${t("filterAll")} (${t("selectClinic")})</option>
                            ${clinicOptions}
                        </select>
                    </div>
                </div>

                <div class="admin-table-wrapper">
                    <table class="admin-table">
                        <thead>
                            <tr>
                                <th>${t("name")} & ${t("email")}</th>
                                <th>${t("clinic")}</th>
                                <th>${t("assignRole")}</th>
                                <th>${t("status")}</th>
                                <th>${t("toggleUserActive")}</th>
                                <th style="text-align:end;">${t("actions")}</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${rows || `<tr><td colspan="6" style="text-align:center;padding:32px;" class="muted">${t("noClinicsFound")}</td></tr>`}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
}

// ------------------------------------------
// Super Admin Action Modals
// ------------------------------------------
function adminOpenCreateClinicModal() {
    modal(t("createClinicTitle"), `
        <form id="adminCreateClinicForm" class="form-grid">
            <div class="field full-span">
                <label>${t("clinicNameLabel")}</label>
                <input name="name" required placeholder="e.g. Damascus Dental Center">
            </div>
            <div class="field">
                <label>${t("phone")}</label>
                <input name="phone" placeholder="+963 ...">
            </div>
            <div class="field">
                <label>${t("currency")}</label>
                <select name="currency">
                    <option value="SYR">SYR</option>
                    <option value="USD">USD</option>
                    <option value="EUR">EUR</option>
                </select>
            </div>
            <div class="field full-span">
                <label>${t("address")}</label>
                <input name="address" placeholder="Address...">
            </div>
            <div class="field">
                <label>${t("subscriptionStatus")}</label>
                <select name="subscription_status">
                    <option value="active">Active</option>
                    <option value="trial">Trial</option>
                </select>
            </div>
            <div class="field">
                <label>${t("subscriptionExpires")}</label>
                <input type="date" name="subscription_expires_at">
            </div>
            <hr class="full-span" style="border:none;border-top:1px solid var(--border);margin:8px 0;">
            <div class="field full-span">
                <label>${t("headDoctorNameLabel")}</label>
                <input name="head_doctor_name" required placeholder="Dr. First Last">
            </div>
            <div class="field">
                <label>${t("headDoctorEmailLabel")}</label>
                <input name="head_doctor_email" type="email" required placeholder="doctor@clinic.com">
            </div>
            <div class="field">
                <label>${t("headDoctorPasswordLabel")}</label>
                <input name="head_doctor_password" type="password" minlength="8" required placeholder="••••••••">
            </div>
            <div class="form-actions full-span">
                <button class="button button-primary" type="submit">${t("save")}</button>
            </div>
        </form>
    `);

    $("#adminCreateClinicForm").onsubmit = async (e) => {
        e.preventDefault();
        const data = Object.fromEntries(new FormData(e.target));
        if (data.subscription_expires_at) {
            data.subscription_expires_at = new Date(data.subscription_expires_at).toISOString();
        } else {
            delete data.subscription_expires_at;
        }
        try {
            await window.AERODENT_API.post("/api/admin/clinics", data);
            $("#modal").classList.remove("show");
            toast(t("clinicCreated"));
            await loadAdminClinics();
            await loadAdminMetrics();
            render();
        } catch (err) {
            toast(err.message || "Failed to create clinic");
        }
    };
}

function adminOpenManageSubscriptionModal(clinicId) {
    const clinic = (state.adminClinics || []).find((c) => c.id === clinicId);
    if (!clinic) return;

    const expiresIso = clinic.subscription_expires_at ? clinic.subscription_expires_at.slice(0, 10) : "";

    modal(`${t("extendSubscription")} - ${esc(clinic.name)}`, `
        <form id="adminManageSubForm" class="form-grid">
            <div class="field full-span">
                <label>${t("subscriptionStatus")}</label>
                <select name="subscription_status">
                    <option value="active" ${clinic.subscription_status === "active" ? "selected" : ""}>Active</option>
                    <option value="trial" ${clinic.subscription_status === "trial" ? "selected" : ""}>Trial</option>
                    <option value="past_due" ${clinic.subscription_status === "past_due" ? "selected" : ""}>Past Due</option>
                    <option value="suspended" ${clinic.subscription_status === "suspended" ? "selected" : ""}>Suspended</option>
                    <option value="cancelled" ${clinic.subscription_status === "cancelled" ? "selected" : ""}>Cancelled</option>
                </select>
            </div>
            <div class="field full-span">
                <label>${t("subscriptionExpires")}</label>
                <input type="date" name="subscription_expires_at" value="${expiresIso}">
            </div>
            <div class="field full-span">
                <label>Quick Add Days</label>
                <div style="display:flex;gap:8px;margin-top:4px;">
                    <button type="button" class="button button-ghost button-sm" data-quick-days="30">${t("quickExtend30")}</button>
                    <button type="button" class="button button-ghost button-sm" data-quick-days="90">${t("quickExtend90")}</button>
                    <button type="button" class="button button-ghost button-sm" data-quick-days="365">${t("quickExtend365")}</button>
                </div>
            </div>
            <div class="form-actions full-span">
                <button class="button button-primary" type="submit">${t("save")}</button>
            </div>
        </form>
    `);

    $$("[data-quick-days]").forEach((btn) => {
        btn.onclick = async () => {
            const days = Number(btn.dataset.quickDays);
            try {
                await window.AERODENT_API.patch(`/api/admin/clinics/${clinicId}`, {
                    extend_days: days,
                    subscription_status: "active",
                    is_active: true,
                });
                $("#modal").classList.remove("show");
                toast(t("subscriptionUpdated"));
                await loadAdminClinics();
                await loadAdminMetrics();
                render();
            } catch (err) {
                toast(err.message || "Failed to extend subscription");
            }
        };
    });

    $("#adminManageSubForm").onsubmit = async (e) => {
        e.preventDefault();
        const data = Object.fromEntries(new FormData(e.target));
        const payload = {
            subscription_status: data.subscription_status,
        };
        if (data.subscription_expires_at) {
            payload.subscription_expires_at = new Date(data.subscription_expires_at).toISOString();
        } else {
            payload.subscription_expires_at = null;
        }

        try {
            await window.AERODENT_API.patch(`/api/admin/clinics/${clinicId}`, payload);
            $("#modal").classList.remove("show");
            toast(t("subscriptionUpdated"));
            await loadAdminClinics();
            await loadAdminMetrics();
            render();
        } catch (err) {
            toast(err.message || "Failed to update subscription");
        }
    };
}

function adminOpenEditClinicModal(clinicId) {
    const clinic = (state.adminClinics || []).find((c) => c.id === clinicId);
    if (!clinic) return;

    modal(`${t("edit")} - ${esc(clinic.name)}`, `
        <form id="adminEditClinicForm" class="form-grid">
            <div class="field full-span">
                <label>${t("clinicNameLabel")}</label>
                <input name="name" value="${esc(clinic.name)}" required>
            </div>
            <div class="field">
                <label>${t("phone")}</label>
                <input name="phone" value="${esc(clinic.phone || "")}">
            </div>
            <div class="field">
                <label>${t("currency")}</label>
                <select name="currency">
                    <option value="SYR" ${clinic.currency === "SYR" ? "selected" : ""}>SYR</option>
                    <option value="USD" ${clinic.currency === "USD" ? "selected" : ""}>USD</option>
                    <option value="EUR" ${clinic.currency === "EUR" ? "selected" : ""}>EUR</option>
                </select>
            </div>
            <div class="field full-span">
                <label>${t("address")}</label>
                <input name="address" value="${esc(clinic.address || "")}">
            </div>
            <div class="form-actions full-span" style="margin-top:12px;">
                <button class="button button-primary" type="submit">${t("save")}</button>
            </div>
        </form>
        <div class="admin-danger-zone" style="margin-top:24px;padding:16px 18px;border:1px solid #fecaca;border-radius:10px;background:#fef2f2;">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
                <div>
                    <div style="font-weight:700;color:#991b1b;font-size:13px;">${t("deleteClinic")}</div>
                    <small style="color:#b91c1c;display:block;margin-top:2px;">${t("confirmDeleteClinic")}</small>
                </div>
                <button type="button" class="btn-admin-action btn-admin-danger" id="adminModalDeleteClinicBtn">${t("deleteClinic")}</button>
            </div>
        </div>
    `);

    const delBtn = $("#adminModalDeleteClinicBtn");
    if (delBtn) {
        delBtn.onclick = () => adminDeleteClinic(clinicId);
    }

    $("#adminEditClinicForm").onsubmit = async (e) => {
        e.preventDefault();
        const data = Object.fromEntries(new FormData(e.target));
        try {
            await window.AERODENT_API.patch(`/api/admin/clinics/${clinicId}`, data);
            $("#modal").classList.remove("show");
            toast(t("clinicCreated"));
            await loadAdminClinics();
            render();
        } catch (err) {
            toast(err.message || "Failed to update clinic");
        }
    };
}

async function adminToggleClinicActive(clinicId, currentActive) {
    const actionDesc = currentActive ? "Deactivate" : "Activate";
    if (currentActive && !confirm(`${t("clinicDeactivateWarning")}\n\nAre you sure you want to deactivate this clinic?`)) {
        return;
    }
    try {
        await window.AERODENT_API.patch(`/api/admin/clinics/${clinicId}`, {
            is_active: !currentActive,
        });
        toast(`Clinic ${actionDesc.toLowerCase()}d successfully.`);
        await loadAdminClinics();
        await loadAdminMetrics();
        render();
    } catch (err) {
        toast(err.message || "Failed to update clinic status");
    }
}

async function adminToggleUserActive(userId, currentActive, role) {
    if (userId === state.auth?.user?.id) {
        toast(t("cannotDeactivateSelf"));
        return;
    }

    if (role === "head_doctor" && currentActive) {
        const confirmed = confirm(`${t("cascadeDeactivateWarning")}\n\nAre you sure you want to deactivate this Head Doctor?`);
        if (!confirmed) return;
    }

    try {
        await window.AERODENT_API.patch(`/api/admin/users/${userId}`, {
            is_active: !currentActive,
        });
        toast(t("userSaved"));
        await loadAdminUsers();
        await loadAdminClinics();
        await loadAdminMetrics();
        render();
    } catch (err) {
        toast(err.message || "Failed to update user status");
    }
}

function adminOpenCreateUserModal() {
    const clinics = state.adminClinics || [];
    const clinicOptions = clinics.map((c) => `<option value="${c.id}">${esc(c.name)} (#${c.id})</option>`).join("");

    modal(t("createUser"), `
        <form id="adminCreateUserForm" class="form-grid">
            <div class="field full-span">
                <label>${t("selectClinic")}</label>
                <select name="clinic_id" required>
                    ${clinicOptions}
                </select>
            </div>
            <div class="field full-span">
                <label>${t("name")}</label>
                <input name="name" required>
            </div>
            <div class="field full-span">
                <label>${t("email")}</label>
                <input name="email" type="email" required>
            </div>
            <div class="field full-span">
                <label>${t("password")}</label>
                <input name="password" type="password" minlength="8" required>
            </div>
            <div class="field full-span">
                <label>${t("assignRole")}</label>
                <select name="role" required>
                    <option value="doctor">${t("doctorRole")}</option>
                    <option value="secretary">${t("secretaryRole")}</option>
                    <option value="head_doctor">${t("headDoctorRole")}</option>
                </select>
            </div>
            <div class="form-actions full-span">
                <button class="button button-primary" type="submit">${t("save")}</button>
            </div>
        </form>
    `);

    $("#adminCreateUserForm").onsubmit = async (e) => {
        e.preventDefault();
        const data = Object.fromEntries(new FormData(e.target));
        data.clinic_id = Number(data.clinic_id);
        try {
            await window.AERODENT_API.post("/api/admin/users", data);
            $("#modal").classList.remove("show");
            toast(t("userSaved"));
            await loadAdminUsers();
            await loadAdminClinics();
            await loadAdminMetrics();
            render();
        } catch (err) {
            toast(err.message || "Failed to create user");
        }
    };
}

function adminOpenEditUserModal(userId) {
    const user = (state.adminUsers || []).find((u) => u.id === userId);
    if (!user) return;

    modal(`${t("editUser")} - ${esc(user.name)}`, `
        <form id="adminEditUserForm" class="form-grid">
            <div class="field full-span">
                <label>${t("name")}</label>
                <input name="name" value="${esc(user.name)}" required>
            </div>
            <div class="field full-span">
                <label>${t("email")}</label>
                <input name="email" type="email" value="${esc(user.email)}" required>
            </div>
            <div class="field full-span">
                <label>${t("assignRole")}</label>
                <select name="role">
                    <option value="doctor" ${user.role === "doctor" ? "selected" : ""}>${t("doctorRole")}</option>
                    <option value="secretary" ${user.role === "secretary" ? "selected" : ""}>${t("secretaryRole")}</option>
                    <option value="head_doctor" ${user.role === "head_doctor" ? "selected" : ""}>${t("headDoctorRole")}</option>
                    <option value="super_admin" ${user.role === "super_admin" ? "selected" : ""}>${t("superAdminRole")}</option>
                </select>
            </div>
            <div class="field full-span">
                <label>${t("resetPassword")} (${t("optional") || "leave blank to keep unchanged"})</label>
                <input name="password" type="password" minlength="8" placeholder="••••••••">
            </div>
            <div class="form-actions full-span">
                <button class="button button-primary" type="submit">${t("save")}</button>
            </div>
        </form>
    `);

    $("#adminEditUserForm").onsubmit = async (e) => {
        e.preventDefault();
        const data = Object.fromEntries(new FormData(e.target));
        const payload = {
            name: data.name,
            email: data.email,
            role: data.role,
        };
        if (data.password && data.password.trim()) {
            payload.password = data.password.trim();
        }
        try {
            await window.AERODENT_API.patch(`/api/admin/users/${userId}`, payload);
            $("#modal").classList.remove("show");
            toast(t("userSaved"));
            await loadAdminUsers();
            await loadAdminClinics();
            await loadAdminMetrics();
            render();
        } catch (err) {
            toast(err.message || "Failed to update user");
        }
    };
}

async function adminDeleteUser(userId) {
    if (!confirm(t("confirmDeleteStaff"))) return;
    try {
        await window.AERODENT_API.delete(`/api/admin/users/${userId}`);
        toast(t("staffDeleted"));
        await loadAdminUsers();
        await loadAdminClinics();
        await loadAdminMetrics();
        render();
    } catch (err) {
        toast(err.message || "Failed to delete user");
    }
}

async function adminDeleteClinic(clinicId) {
    const clinic = (state.adminClinics || []).find((c) => c.id === clinicId);
    const clinicName = clinic ? clinic.name : `#${clinicId}`;
    const confirmed = confirm(
        `${t("confirmDeleteClinic")}\n\nClinic: "${clinicName}"\n\n⚠️ ${t("deleteClinicWarning") || "Deleting this clinic will permanently delete all of its staff accounts (head doctors, doctors, secretaries), patients, appointments, and data."}`
    );
    if (!confirmed) return;

    try {
        await window.AERODENT_API.delete(`/api/admin/clinics/${clinicId}`);
        $("#modal")?.classList.remove("show");
        toast(t("clinicDeleted"));
        await loadAdminClinics();
        await loadAdminUsers();
        await loadAdminMetrics();
        render();
    } catch (err) {
        toast(err.message || "Failed to delete clinic");
    }
}

