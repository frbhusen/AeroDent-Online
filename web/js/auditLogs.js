// ==========================================
// AeroDent Activity Audit Log UI
// Healthcare Compliance & Activity Tracking
// Full Bilingual (Arabic / English) Support
// ==========================================

async function loadAuditLogs(clinicId = null, action = "", resourceType = "") {
    if (!window.AERODENT_ONLINE) return;
    state.auditLogsLoading = true;
    try {
        const params = new URLSearchParams();
        if (clinicId) params.append("clinic_id", clinicId);
        if (action && action !== "all") params.append("action", action);
        if (resourceType && resourceType !== "all") params.append("resource_type", resourceType);
        params.append("limit", "150");

        const query = params.toString() ? `?${params.toString()}` : "";
        const res = await window.AERODENT_API.get(`/api/audit-logs${query}`);
        state.auditLogs = res.data || [];
        state.auditLogsTotal = res.total || (res.data ? res.data.length : 0);
    } catch (err) {
        console.error("Failed to load audit logs:", err);
        state.auditLogs = [];
    } finally {
        state.auditLogsLoading = false;
    }
}

function _auditActionBadge(action) {
    if (!action) return `<span class="badge badge-gray">-</span>`;
    const act = String(action).toLowerCase();
    let color = "#475569";
    let bg = "#f1f5f9";
    let border = "#cbd5e1";

    if (act.includes("create") || act.includes("registered") || act.includes("issued") || act.includes("uploaded")) {
        color = "#15803d";
        bg = "#dcfce7";
        border = "#bbf7d0";
    } else if (act.includes("delete") || act.includes("void") || act.includes("cancelled") || act.includes("cancel")) {
        color = "#b91c1c";
        bg = "#fee2e2";
        border = "#fecaca";
    } else if (act.includes("update") || act.includes("change") || act.includes("edit")) {
        color = "#b45309";
        bg = "#fef3c7";
        border = "#fde68a";
    } else if (act.includes("payment")) {
        color = "#047857";
        bg = "#d1fae5";
        border = "#a7f3d0";
    } else if (act.includes("login") || act.includes("logout") || act.includes("auth")) {
        color = "#0369a1";
        bg = "#e0f2fe";
        border = "#bae6fd";
    }

    const key = "action_" + act;
    const translated = t(key);
    const label = (translated && translated !== key) ? translated : esc(action.replace(/_/g, " "));

    return `<span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;color:${color};background:${bg};border:1px solid ${border};white-space:nowrap;">${label}</span>`;
}

function _formatAuditRole(role) {
    if (!role) return "-";
    const r = String(role).toLowerCase();
    if (r === "head_doctor") return t("headDoctorRole") || t("headDoctor") || "Head Doctor";
    if (r === "doctor") return t("doctorRole") || "Doctor";
    if (r === "secretary") return t("secretaryRole") || "Secretary";
    if (r === "super_admin") return t("superAdminRole") || "Super Admin";
    return esc(role.replace(/_/g, " "));
}

function _formatAuditResource(resourceType) {
    if (!resourceType) return "-";
    const key = "resource_" + String(resourceType).toLowerCase();
    const translated = t(key);
    if (translated && translated !== key) return translated;
    return esc(String(resourceType).replace(/_/g, " "));
}

function _formatAuditDetails(detailsStr) {
    if (!detailsStr) return "-";
    try {
        const parsed = JSON.parse(detailsStr);
        if (typeof parsed === "object" && parsed !== null) {
            const entries = Object.entries(parsed);
            if (!entries.length) return "-";
            return entries
                .map(([k, v]) => {
                    const key = "detail_" + String(k).toLowerCase();
                    const translatedKey = t(key);
                    const label = (translatedKey && translatedKey !== key) ? translatedKey : esc(String(k).replace(/_/g, " "));
                    let valDisplay = String(v);
                    if (v === true) valDisplay = currentLanguage === "ar" ? "نعم" : "Yes";
                    else if (v === false) valDisplay = currentLanguage === "ar" ? "لا" : "No";
                    else if (k === "payment_method") {
                        if (valDisplay === "cash") valDisplay = currentLanguage === "ar" ? "نقداً" : "Cash";
                        else if (valDisplay === "card") valDisplay = currentLanguage === "ar" ? "بطاقة" : "Card";
                        else if (valDisplay === "bank_transfer") valDisplay = currentLanguage === "ar" ? "تحويل بنكي" : "Bank Transfer";
                        else if (valDisplay === "insurance") valDisplay = currentLanguage === "ar" ? "تأمين" : "Insurance";
                    }
                    return `<span style="display:inline-block;margin:1px 4px 1px 0;"><b>${label}</b>: <span style="color:#0f172a;font-weight:500;">${esc(valDisplay)}</span></span>`;
                })
                .join("<span style=\"color:#94a3b8;margin:0 6px;\" aria-hidden=\"true\">·</span>");
        }
        return esc(String(parsed));
    } catch {
        return esc(String(detailsStr));
    }
}

function renderAuditLogs() {
    const logs = state.auditLogs || [];
    const isSuperAdmin = state.auth?.user?.role === "super_admin";
    const activeCategory = state.auditFilterCategory || "all";
    const searchQuery = (state.auditSearchQuery || "").trim().toLowerCase();

    // Category filtering
    let filtered = logs.filter((l) => {
        if (activeCategory === "all") return true;
        const res = String(l.resource_type || "").toLowerCase();
        const act = String(l.action || "").toLowerCase();

        if (activeCategory === "auth") {
            return res === "auth" || res === "user" || act.includes("login") || act.includes("logout") || act.includes("password");
        }
        if (activeCategory === "patients") {
            return res === "patient" || act.includes("patient");
        }
        if (activeCategory === "financial") {
            return res === "invoice" || res === "payment" || act.includes("payment") || act.includes("invoice");
        }
        if (activeCategory === "clinical") {
            return (
                res === "treatment" ||
                res === "treatment_plan" ||
                res === "prescription" ||
                res === "xray" ||
                res === "odontogram" ||
                res === "appointment" ||
                act.includes("treatment") ||
                act.includes("prescription") ||
                act.includes("xray") ||
                act.includes("odontogram") ||
                act.includes("appointment")
            );
        }
        return true;
    });

    // Search query filtering
    if (searchQuery) {
        filtered = filtered.filter((l) => {
            const userName = String(l.user_name || "").toLowerCase();
            const userRole = String(l.user_role || "").toLowerCase();
            const roleFormatted = _formatAuditRole(l.user_role).toLowerCase();
            const action = String(l.action || "").toLowerCase();
            const actionBadgeText = (t("action_" + action) || "").toLowerCase();
            const resource = String(l.resource_type || "").toLowerCase();
            const resourceFormatted = _formatAuditResource(l.resource_type).toLowerCase();
            const resourceId = String(l.resource_id || "").toLowerCase();
            const details = String(l.details || "").toLowerCase();
            const ip = String(l.ip_address || "").toLowerCase();

            return (
                userName.includes(searchQuery) ||
                userRole.includes(searchQuery) ||
                roleFormatted.includes(searchQuery) ||
                action.includes(searchQuery) ||
                actionBadgeText.includes(searchQuery) ||
                resource.includes(searchQuery) ||
                resourceFormatted.includes(searchQuery) ||
                resourceId.includes(searchQuery) ||
                details.includes(searchQuery) ||
                ip.includes(searchQuery)
            );
        });
    }

    const rows = filtered.map((l) => {
        const timeFormatted = l.created_at
            ? new Date(l.created_at).toLocaleString(currentLanguage === "ar" ? "ar-SA" : "en-US", {
                year: "numeric",
                month: "short",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
            })
            : "-";

        const detailsDisplay = _formatAuditDetails(l.details);
        const resourceTranslated = _formatAuditResource(l.resource_type);
        const roleTranslated = _formatAuditRole(l.user_role);

        return `
            <tr>
                <td style="white-space:nowrap;font-size:12px;color:#64748b;" dir="ltr">${timeFormatted}</td>
                <td>
                    <b style="color:#0f172a;">${esc(l.user_name || "-")}</b>
                    <br><small class="muted" style="font-size:11px;">${roleTranslated}</small>
                </td>
                ${isSuperAdmin ? `<td><span class="badge badge-gray" dir="ltr">${l.clinic_id ? `#${esc(l.clinic_id)}` : (t("globalPlatform") || "Global")}</span></td>` : ""}
                <td>${_auditActionBadge(l.action)}</td>
                <td>
                    <span style="font-weight:600;color:#334155;">${resourceTranslated}</span>
                    ${l.resource_id ? `<small class="muted" dir="ltr" style="font-size:11px;margin-inline-start:4px;">(#${esc(l.resource_id)})</small>` : ""}
                </td>
                <td style="font-size:12px;max-width:340px;line-height:1.5;">${detailsDisplay}</td>
                <td style="font-size:11px;color:#64748b;font-family:monospace;white-space:nowrap;" dir="ltr">${esc(l.ip_address || "-")}</td>
            </tr>
        `;
    }).join("");

    const colSpan = isSuperAdmin ? 7 : 6;

    const categories = [
        { id: "all", label: t("filterCategoryAll") || "All Events" },
        { id: "auth", label: t("filterCategoryAuth") || "Logins & Security" },
        { id: "patients", label: t("filterCategoryPatients") || "Patients" },
        { id: "financial", label: t("filterCategoryFinancial") || "Financial & Billing" },
        { id: "clinical", label: t("filterCategoryClinical") || "Clinical & Visits" },
    ];

    const categoryChips = categories.map((cat) => {
        const isActive = activeCategory === cat.id;
        const activeStyle = isActive
            ? "background:#0369a1;color:#fff;border-color:#0369a1;font-weight:600;"
            : "background:#f8fafc;color:#475569;border-color:#e2e8f0;";
        return `
            <button
                type="button"
                class="audit-filter-chip"
                data-audit-category="${cat.id}"
                style="padding:6px 14px;border-radius:20px;border:1px solid;font-size:12px;cursor:pointer;transition:all 0.15s ease;${activeStyle}">
                ${cat.label}
            </button>
        `;
    }).join("");

    return `
        <div class="admin-container">
            <div class="admin-card" style="box-shadow:0 4px 20px -2px rgba(0,0,0,0.06);border:1px solid #e2e8f0;border-radius:14px;overflow:hidden;">
                <!-- Header Toolbar -->
                <div class="admin-card-header" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px;padding:20px 24px;border-bottom:1px solid #f1f5f9;background:#fff;">
                    <div>
                        <h2 style="margin:0 0 4px 0;font-size:20px;font-weight:700;color:#0f172a;display:flex;align-items:center;gap:8px;">
                            <span>📜</span>
                            <span>${t("auditLogs")}</span>
                            <span class="badge badge-gray" style="font-size:12px;padding:3px 10px;border-radius:12px;margin-inline-start:8px;" dir="ltr">
                                ${filtered.length} / ${logs.length}
                            </span>
                        </h2>
                        <p style="margin:0;font-size:13px;color:#64748b;">${t("auditLogsSubtitle") || "Immutable clinical activity trail and access log"}</p>
                    </div>
                    <div style="display:flex;align-items:center;gap:10px;">
                        <button class="btn-admin-action" id="refreshAuditBtn" type="button" style="display:inline-flex;align-items:center;gap:6px;padding:8px 16px;border-radius:8px;font-size:13px;font-weight:600;">
                            <span>🔄</span>
                            <span>${t("refresh") || "Refresh"}</span>
                        </button>
                    </div>
                </div>

                <!-- Filters & Search Toolbar -->
                <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;padding:14px 24px;background:#f8fafc;border-bottom:1px solid #e2e8f0;">
                    <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                        ${categoryChips}
                    </div>
                    <div style="min-width:240px;position:relative;">
                        <input
                            type="search"
                            id="auditSearchInput"
                            placeholder="${t("auditSearchPlaceholder")}"
                            value="${esc(state.auditSearchQuery || "")}"
                            style="width:100%;padding:7px 14px;border-radius:8px;border:1px solid #cbd5e1;font-size:13px;outline:none;background:#fff;"
                        />
                    </div>
                </div>

                <!-- Table Content -->
                <div class="admin-table-wrapper" style="overflow-x:auto;">
                    <table class="admin-table" style="width:100%;border-collapse:collapse;">
                        <thead>
                            <tr style="background:#f8fafc;border-bottom:1px solid #e2e8f0;">
                                <th style="padding:12px 16px;font-size:12px;font-weight:600;color:#475569;text-align:start;">${t("timestamp") || "Timestamp"}</th>
                                <th style="padding:12px 16px;font-size:12px;font-weight:600;color:#475569;text-align:start;">${t("user") || "User"}</th>
                                ${isSuperAdmin ? `<th style="padding:12px 16px;font-size:12px;font-weight:600;color:#475569;text-align:start;">${t("clinic") || "Clinic"}</th>` : ""}
                                <th style="padding:12px 16px;font-size:12px;font-weight:600;color:#475569;text-align:start;">${t("action") || "Action"}</th>
                                <th style="padding:12px 16px;font-size:12px;font-weight:600;color:#475569;text-align:start;">${t("resource") || "Resource"}</th>
                                <th style="padding:12px 16px;font-size:12px;font-weight:600;color:#475569;text-align:start;">${t("details") || "Details"}</th>
                                <th style="padding:12px 16px;font-size:12px;font-weight:600;color:#475569;text-align:start;">${t("ipAddress") || "IP Address"}</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${
                                rows ||
                                `<tr>
                                    <td colspan="${colSpan}" style="text-align:center;padding:48px 24px;" class="muted">
                                        <div style="font-size:32px;margin-bottom:8px;">📜</div>
                                        <div style="font-size:14px;font-weight:500;">
                                            ${state.auditLogsLoading ? (t("loadingAuditLogs") || "Loading activity logs...") : (t("noAuditLogs") || "No activity logs recorded yet.")}
                                        </div>
                                    </td>
                                </tr>`
                            }
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
}

function bindAuditLogEvents() {
    $$("[data-audit-category]").forEach((btn) => {
        btn.onclick = () => {
            const cat = btn.dataset.auditCategory || "all";
            state.auditFilterCategory = cat;
            render();
        };
    });

    const searchInput = $("#auditSearchInput");
    if (searchInput) {
        searchInput.oninput = (e) => {
            state.auditSearchQuery = e.target.value;
            render();
            const newInput = $("#auditSearchInput");
            if (newInput) {
                newInput.focus();
                const len = newInput.value.length;
                newInput.setSelectionRange(len, len);
            }
        };
    }
}
