// ==========================================
// AeroDent Spotlight Command Palette (Ctrl + K)
// Fast Keyboard Navigation & Patient Search
// ==========================================

function openCommandPalette() {
    let modal = $("#commandPaletteModal");
    if (!modal) {
        modal = document.createElement("div");
        modal.id = "commandPaletteModal";
        modal.className = "modal";
        modal.innerHTML = `
            <div class="modal-card" style="max-width:580px;padding:16px 20px;border-radius:14px;box-shadow:0 24px 60px rgba(15,23,42,0.22);">
                <div style="display:flex;align-items:center;gap:10px;border-bottom:1px solid #e2e8f0;padding-bottom:12px;">
                    <span style="font-size:18px;color:#94a3b8;">🔍</span>
                    <input type="text" id="cmdPaletteInput" placeholder="${t("searchPatientsPrompt") || "Search patients or actions (Ctrl + K)..."}" autocomplete="off" style="border:none;outline:none;font-size:15px;width:100%;background:transparent;color:#0f172a;">
                    <span style="font-size:10px;padding:3px 7px;border-radius:5px;background:#f1f5f9;color:#475569;font-weight:600;border:1px solid #e2e8f0;">ESC</span>
                </div>
                <div id="cmdPaletteResults" style="max-height:360px;overflow-y:auto;margin-top:10px;"></div>
            </div>
        `;
        document.body.appendChild(modal);

        modal.onclick = (e) => {
            if (e.target === modal) closeCommandPalette();
        };

        const input = $("#cmdPaletteInput");
        input.oninput = (e) => renderCommandPaletteResults(e.target.value.trim());
        input.onkeydown = (e) => {
            if (e.key === "Escape") closeCommandPalette();
        };
    }

    modal.classList.add("show");
    const input = $("#cmdPaletteInput");
    if (input) {
        input.value = "";
        input.focus();
        renderCommandPaletteResults("");
    }
}

function closeCommandPalette() {
    const modal = $("#commandPaletteModal");
    if (modal) modal.classList.remove("show");
}

function renderCommandPaletteResults(query = "") {
    const resultsContainer = $("#cmdPaletteResults");
    if (!resultsContainer) return;

    const lowerQuery = query.toLowerCase();
    const isSuperAdmin = state.auth?.user?.role === "super_admin";

    // 1. Navigation / Quick actions
    const defaultActions = [
        { id: "new_patient", title: t("newPatient") || "New Patient", icon: "＋", action: () => { closeCommandPalette(); actions("newPatient"); } },
        { id: "new_appt", title: t("addAppointment") || "Book Appointment", icon: "📅", action: () => { closeCommandPalette(); actions("addAppointment"); } },
        { id: "view_odontogram", title: t("odontogram") || "Odontogram", icon: "◈", action: () => { closeCommandPalette(); state.view = "odontogram"; render(); } },
        { id: "view_appts", title: t("appointments") || "Appointments Calendar", icon: "▦", action: () => { closeCommandPalette(); state.view = "appointments"; render(); } },
        { id: "view_invoices", title: t("invoices") || "Invoices & Payments", icon: "💳", action: () => { closeCommandPalette(); state.view = "treatments"; render(); } },
    ];

    if (isSuperAdmin) {
        defaultActions.unshift(
            { id: "admin_clinics", title: t("adminClinics") || "Clinics Control", icon: "🏥", action: () => { closeCommandPalette(); state.view = "admin_clinics"; render(); } },
            { id: "admin_users", title: t("adminUsers") || "Staff Accounts", icon: "👥", action: () => { closeCommandPalette(); state.view = "admin_users"; render(); } }
        );
    }

    if (isSuperAdmin || state.auth?.user?.role === "head_doctor") {
        defaultActions.push({
            id: "view_audit",
            title: t("auditLogs") || "Activity Audit Log",
            icon: "📜",
            action: async () => {
                closeCommandPalette();
                state.view = "audit_logs";
                if (typeof loadAuditLogs === "function") await loadAuditLogs();
                render();
            }
        });
    }

    if (window.AERODENT_ONLINE && !isSuperAdmin && hasPermission("inventory.read")) {
        defaultActions.push({
            id: "view_inventory",
            title: t("inventory"),
            icon: "📦",
            action: async () => {
                closeCommandPalette();
                state.view = "inventory";
                render();
                await reloadInventoryView();
            }
        });
    }

    const filteredActions = defaultActions.filter((a) => a.title.toLowerCase().includes(lowerQuery));

    // 2. Patients search
    const patients = state.patients || [];
    const matchedPatients = query
        ? patients.filter((p) =>
            (p.name && p.name.toLowerCase().includes(lowerQuery)) ||
            (p.phone && p.phone.includes(query)) ||
            String(p.id).includes(query)
        ).slice(0, 6)
        : patients.slice(0, 4);

    let html = "";

    if (matchedPatients.length > 0) {
        html += `<div style="font-size:11px;font-weight:700;color:var(--muted);padding:6px 8px;text-transform:uppercase;letter-spacing:0.5px;">${t("cmdPatients")}</div>`;
        matchedPatients.forEach((p) => {
            html += `
                <div class="cmd-item" data-cmd-patient="${p.id}" style="display:flex;align-items:center;justify-content:space-between;padding:8px 12px;border-radius:8px;cursor:pointer;margin-bottom:2px;transition:background 0.1s ease;">
                    <div style="display:flex;align-items:center;gap:10px;">
                        <span style="font-size:16px;">👤</span>
                        <div>
                            <div style="font-weight:600;font-size:13px;color:#0f172a;">${esc(p.name)} <small style="color:#64748b;font-weight:normal;">#${p.id}</small></div>
                            <small style="color:var(--muted);">${esc(p.phone || t("noPhone"))} ${p.dob ? "· " + esc(p.dob) : ""}</small>
                        </div>
                    </div>
                    <span style="font-size:11px;color:var(--primary);font-weight:600;">${t("cmdSelect")}</span>
                </div>
            `;
        });
    }

    if (filteredActions.length > 0) {
        html += `<div style="font-size:11px;font-weight:700;color:var(--muted);padding:8px 8px 6px;text-transform:uppercase;letter-spacing:0.5px;">${t("cmdQuickActions")}</div>`;
        filteredActions.forEach((a, idx) => {
            html += `
                <div class="cmd-item" data-cmd-action-idx="${idx}" style="display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:8px;cursor:pointer;margin-bottom:2px;transition:background 0.1s ease;">
                    <span style="font-size:16px;">${a.icon}</span>
                    <span style="font-size:13px;font-weight:500;color:#1e293b;">${esc(a.title)}</span>
                </div>
            `;
        });
    }

    if (!html) {
        html = `<div style="text-align:center;padding:24px;color:var(--muted);font-size:13px;">${t("cmdNoResults")} "${esc(query)}"</div>`;
    }

    resultsContainer.innerHTML = html;

    // Hover effect styles
    resultsContainer.querySelectorAll(".cmd-item").forEach((item) => {
        item.onmouseenter = () => item.style.background = "#f1f5f9";
        item.onmouseleave = () => item.style.background = "transparent";
    });

    // Bind patient clicks
    resultsContainer.querySelectorAll("[data-cmd-patient]").forEach((el) => {
        el.onclick = () => {
            const patientId = Number(el.dataset.cmdPatient);
            const found = (state.patients || []).find((p) => p.id === patientId);
            if (found) {
                state.selectedPatient = found;
                closeCommandPalette();
                render();
            }
        };
    });

    // Bind action clicks
    resultsContainer.querySelectorAll("[data-cmd-action-idx]").forEach((el) => {
        el.onclick = () => {
            const idx = Number(el.dataset.cmdActionIdx);
            if (filteredActions[idx]) filteredActions[idx].action();
        };
    });
}

// Global Keyboard Shortcut listener
window.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        openCommandPalette();
    }
});

// Auto-adapt shortcut badge on Apple devices
document.addEventListener("DOMContentLoaded", () => {
    const kbd = document.querySelector(".kbd-shortcut");
    if (kbd && /Mac|iPhone|iPad|iPod/i.test(navigator.userAgent || navigator.platform)) {
        kbd.textContent = "⌘ K";
    }
});

