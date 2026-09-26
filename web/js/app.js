async function refresh(preserveEmptySelection = false) {
  if (window.AERODENT_ONLINE) {
    await refreshOnlinePatients(preserveEmptySelection);
    return;
  }
  [
    state.patients,
    state.odontograms,
    state.appointments,
    state.treatments,
    state.treatmentPlans,
    state.invoices,
    state.prescriptions,
    state.xrays,
  ] = await Promise.all(
    [
      "patients",
      "odontograms",
      "appointments",
      "treatments",
      "treatmentPlans",
      "invoices",
      "prescriptions",
      "xrays",
    ].map(dbGetAll),
  );

  const savedSettings = (await dbGetAll("settings"))[0] || {};

  state.settings = {
    id: 1,
    currencySymbol: "SYR",
    clinicName: "------ Dental Clinic",
    doctorName: "Dr. ------",
    phone: "",
    address: "",
    workStartHour: "09:00",
    workEndHour: "18:00",
    slotDuration: 30,
    currentLanguage: "ar",
    pinEnabled: false,
    pinHash: "",
    ...savedSettings,
  };
  currentLanguage = state.settings.currentLanguage || "ar";
  state.selectedPatient = preserveEmptySelection
    ? null
    : state.selectedPatient
      ? state.patients.find(
        (patient) => patient.id === state.selectedPatient.id,
      ) ||
      state.patients[0] ||
      null
      : state.patients[0] || null;

  const patientIds = new Set(state.patients.map((patient) => patient.id));

  if (
    state.treatmentPatientId !== null &&
    !patientIds.has(Number(state.treatmentPatientId))
  ) {
    state.treatmentPatientId = null;
  }

  if (
    state.treatmentPlanPatientId !== null &&
    !patientIds.has(Number(state.treatmentPlanPatientId))
  ) {
    state.treatmentPlanPatientId = null;
  }

  if (
    state.prescriptionPatientId !== null &&
    !patientIds.has(Number(state.prescriptionPatientId))
  ) {
    state.prescriptionPatientId = null;
  }

  render();
}

let onlineDashboardRequest = 0;
async function loadOnlineDashboard() {
  if (!window.AERODENT_ONLINE) return;
  const requestId = ++onlineDashboardRequest;
  state.dashboardLoading = true;
  try {
    const [response] = await Promise.all([
      window.AERODENT_API.get("/api/dashboard"),
      typeof loadInventoryAlertSummary === "function" ? loadInventoryAlertSummary() : null,
    ]);
    if (requestId !== onlineDashboardRequest) return;
    state.dashboard = response.data || {};
  } catch (error) {
    if (requestId !== onlineDashboardRequest) return;
    state.dashboardError = error.message;
  } finally {
    if (requestId === onlineDashboardRequest) {
      state.dashboardLoading = false;
      if (state.view === "dashboard") render();
    }
  }
}

function _appointmentStatusBadge(status) {
  const s = String(status || "").toLowerCase();
  const label = t(`status${s.charAt(0).toUpperCase() + s.slice(1)}`) || t(s) || s;
  if (s === "completed") return `<span class="badge badge-green">✓ ${label}</span>`;
  if (s === "in_chair" || s === "chair") return `<span class="badge badge-purple">🪑 ${label}</span>`;
  if (s === "arrived") return `<span class="badge badge-amber">📍 ${label}</span>`;
  if (s === "cancelled") return `<span class="badge badge-danger">✕ ${label}</span>`;
  return `<span class="badge badge-blue">⏱ ${label}</span>`;
}

function renderKeyboardShortcutsCard() {
  return `
    <div class="card dashboard-shortcuts-card">
      <div class="shortcuts-card-header">
        <span class="shortcuts-icon">⌨️</span>
        <h3>${t("keyboardShortcuts")}</h3>
      </div>
      <div class="shortcuts-grid">
        <div class="shortcut-item">
          <div class="shortcut-keys"><kbd>Ctrl</kbd> + <kbd>K</kbd></div>
          <span class="shortcut-label">${t("shortcutSearch")}</span>
        </div>
        <div class="shortcut-item">
          <div class="shortcut-keys"><kbd>N</kbd></div>
          <span class="shortcut-label">${t("newPatient")}</span>
        </div>
        <div class="shortcut-item">
          <div class="shortcut-keys"><kbd>A</kbd></div>
          <span class="shortcut-label">${t("addAppointment")}</span>
        </div>
        <div class="shortcut-item">
          <div class="shortcut-keys"><kbd>P</kbd></div>
          <span class="shortcut-label">${t("patients")}</span>
        </div>
        <div class="shortcut-item">
          <div class="shortcut-keys"><kbd>O</kbd></div>
          <span class="shortcut-label">${t("odontogram")}</span>
        </div>
        <div class="shortcut-item">
          <div class="shortcut-keys"><kbd>Esc</kbd></div>
          <span class="shortcut-label">${t("close")}</span>
        </div>
      </div>
    </div>
  `;
}

function _renderDashboardUserBanner() {
  const userName = state.auth?.user?.name || state.settings?.doctorName || "Dr. Hussein";
  const userRole = state.auth?.user?.role || "head_doctor";
  let roleLabel = t("headDoctorRole") || t("headDoctor") || "Head Doctor";
  let roleIcon = "🩺";
  let roleBadgeClass = "badge-role-head";

  if (userRole === "super_admin") {
    roleLabel = t("superAdminRole") || "Super Admin";
    roleIcon = "👑";
    roleBadgeClass = "badge-role-admin";
  } else if (userRole === "doctor") {
    roleLabel = t("doctorRole") || "Doctor";
    roleIcon = "👨‍⚕️";
    roleBadgeClass = "badge-role-doctor";
  } else if (userRole === "secretary") {
    roleLabel = t("secretaryRole") || "Secretary";
    roleIcon = "📋";
    roleBadgeClass = "badge-role-secretary";
  }

  const rawClinicName = state.settings?.clinicName || "";
  const isPlaceholder = !rawClinicName || rawClinicName === "------ Dental Clinic" || /^Clinic #\d+$/.test(rawClinicName);
  const clinicTitle = !isPlaceholder ? rawClinicName : (state.auth?.user ? `Clinic #${state.auth.user.clinic_id}` : t("appName"));

  const todayStr = new Date().toLocaleDateString(currentLanguage === "ar" ? "ar-SA" : "en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return `
    <div class="dashboard-welcome-banner" style="background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:16px 22px;margin-bottom:20px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;box-shadow:0 2px 6px -1px rgba(0,0,0,0.04);">
      <div style="display:flex;align-items:center;gap:14px;">
        <div style="width:48px;height:48px;border-radius:12px;background:#f8fafc;border:1px solid #e2e8f0;display:flex;align-items:center;justify-content:center;font-size:24px;">
          ${roleIcon}
        </div>
        <div>
          <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
            <h2 style="margin:0;font-size:18px;font-weight:700;color:#0f172a;">${esc(userName)}</h2>
            <span class="user-role-badge ${roleBadgeClass}" style="font-size:12px;padding:4px 12px;margin-top:0;display:inline-flex;align-items:center;gap:4px;">
              <span>${roleIcon}</span>
              <span>${roleLabel}</span>
            </span>
          </div>
          <p class="muted" style="margin:3px 0 0 0;font-size:13px;display:flex;align-items:center;gap:6px;">
            <span>🏥</span>
            <span>${esc(clinicTitle)}</span>
          </p>
        </div>
      </div>
      <div style="text-align:${currentLanguage === "ar" ? "left" : "right"};">
        <div style="font-size:13px;font-weight:600;color:#334155;">${t("today")}</div>
        <div class="muted" style="font-size:12px;">${todayStr}</div>
      </div>
    </div>
  `;
}

function renderDashboard() {
  if (window.AERODENT_ONLINE) {
    const d = state.dashboard || {};
    const activeCount = d.active_patients_count ?? state.patients.length;
    const upcomingCount = d.upcoming_appointments_count ?? 0;
    const owed = d.outstanding_balance ?? "0.00";
    const upcoming = d.upcoming_appointments || [];
    const recent = d.recent_patients || state.patients.slice(0, 5);

    return `
      ${_renderDashboardUserBanner()}
      ${typeof renderInventoryDashboardAlert === "function" ? renderInventoryDashboardAlert() : ""}
      <div class="stats-grid">
        <div class="stat stat-card-patients">
          <div class="stat-icon-wrap stat-icon-blue">
            <span class="stat-icon">👥</span>
          </div>
          <div class="stat-info">
            <div class="stat-top">
              <span class="stat-label">${t("activePatients")}</span>
              <span class="stat-pill pill-blue">${t("active")}</span>
            </div>
            <div class="stat-value">${activeCount}</div>
            <div class="stat-sub muted">${t("patients")}</div>
          </div>
        </div>

        <div class="stat stat-card-upcoming">
          <div class="stat-icon-wrap stat-icon-green">
            <span class="stat-icon">📅</span>
          </div>
          <div class="stat-info">
            <div class="stat-top">
              <span class="stat-label">${t("upcoming")}</span>
              <span class="stat-pill pill-green">${t("today")}</span>
            </div>
            <div class="stat-value">${upcomingCount}</div>
            <div class="stat-sub muted">${t("appointments")}</div>
          </div>
        </div>

        <div class="stat stat-card-owed">
          <div class="stat-icon-wrap stat-icon-amber">
            <span class="stat-icon">💳</span>
          </div>
          <div class="stat-info">
            <div class="stat-top">
              <span class="stat-label">${t("outstanding")}</span>
              <span class="stat-pill pill-amber">${t("balance")}</span>
            </div>
            <div class="stat-value">${money(owed)}</div>
            <div class="stat-sub muted">${t("invoice")}</div>
          </div>
        </div>
      </div>

      <div class="content-grid">
        <section class="card dashboard-card">
          <div class="card-heading">
            <div class="card-title-group">
              <span class="card-heading-icon">📅</span>
              <h2>${t("upcoming")}</h2>
            </div>
            <button class="button button-primary" data-action="addAppointment">＋ ${t("addAppointment")}</button>
          </div>
          <div class="dashboard-appointments-list">
            ${upcoming.length ? upcoming.map((item) => `
              <div class="appointment dashboard-appointment">
                <div class="appointment-time-badge">
                  <span class="time-clock">🕒</span>
                  <bdi dir="ltr">${esc(item.date.slice(0, 10))}</bdi>
                  <bdi dir="ltr">${esc(item.start_time || item.startTime || "--:--")}</bdi>
                </div>
                <div class="appointment-body">
                  <b class="appointment-patient-name">${esc(item.patient_name || item.patientName)}</b>
                  <div class="appointment-meta muted">
                    <span>🩺 ${esc(item.procedure || "Clinical visit")}</span>
                    ${item.doctor_name ? `<span>· 👨‍⚕️ ${esc(item.doctor_name)}</span>` : ""}
                  </div>
                </div>
                <div class="appointment-status">
                  ${_appointmentStatusBadge(item.status)}
                </div>
                <div class="appointment-actions">
                  <button class="button button-ghost button-sm" data-edit-appointment="${item.id}">${t("edit")}</button>
                  <button class="appointment-delete" data-delete-appointment="${item.id}" title="${t("deleteAppointment")}" aria-label="${t("deleteAppointment")}">×</button>
                </div>
              </div>`).join("") : `
              <div class="dashboard-empty-state">
                <span class="empty-state-icon">📅</span>
                <p class="muted">${t("noVisits")}</p>
                <button class="button button-ghost" data-action="addAppointment" style="margin-top:10px;">＋ ${t("addAppointment")}</button>
              </div>`}
          </div>
        </section>

        <div class="dashboard-side-column">
          <section class="card dashboard-card">
            <div class="card-heading">
              <div class="card-title-group">
                <span class="card-heading-icon">👥</span>
                <h2>${t("patients")}</h2>
              </div>
              <button class="button button-ghost" data-view="patients">${t("viewAll") || t("patients")}</button>
            </div>
            <div class="dashboard-patients-list">
              ${recent.length ? recent.map(patientRow).join("") : `
                <div class="dashboard-empty-state">
                  <span class="empty-state-icon">👥</span>
                  <p class="muted">${t("noPatients")}</p>
                </div>`}
            </div>
          </section>

          ${renderKeyboardShortcutsCard()}
        </div>
      </div>`;
  }

  const upcoming = state.appointments
    .filter((item) => item.date >= today())
    .sort((a, b) =>
      `${a.date}${a.startTime}`.localeCompare(`${b.date}${b.startTime}`),
    )
    .slice(0, 5);
  const owed = state.invoices.reduce(
    (sum, item) => sum + Number(item.balance || 0),
    0,
  );

  return `
    ${_renderDashboardUserBanner()}
    <div class="stats-grid">
      <div class="stat stat-card-patients">
        <div class="stat-icon-wrap stat-icon-blue">
          <span class="stat-icon">👥</span>
        </div>
        <div class="stat-info">
          <div class="stat-top">
            <span class="stat-label">${t("activePatients")}</span>
            <span class="stat-pill pill-blue">${t("active")}</span>
          </div>
          <div class="stat-value">${state.patients.length}</div>
          <div class="stat-sub muted">${t("patients")}</div>
        </div>
      </div>

      <div class="stat stat-card-upcoming">
        <div class="stat-icon-wrap stat-icon-green">
          <span class="stat-icon">📅</span>
        </div>
        <div class="stat-info">
          <div class="stat-top">
            <span class="stat-label">${t("upcoming")}</span>
            <span class="stat-pill pill-green">${t("today")}</span>
          </div>
          <div class="stat-value">${upcoming.length}</div>
          <div class="stat-sub muted">${t("appointments")}</div>
        </div>
      </div>

      <div class="stat stat-card-owed">
        <div class="stat-icon-wrap stat-icon-amber">
          <span class="stat-icon">💳</span>
        </div>
        <div class="stat-info">
          <div class="stat-top">
            <span class="stat-label">${t("outstanding")}</span>
            <span class="stat-pill pill-amber">${t("balance")}</span>
          </div>
          <div class="stat-value">${money(owed)}</div>
          <div class="stat-sub muted">${t("invoice")}</div>
        </div>
      </div>
    </div>

    <div class="content-grid">
      <section class="card dashboard-card">
        <div class="card-heading">
          <div class="card-title-group">
            <span class="card-heading-icon">📅</span>
            <h2>${t("upcoming")}</h2>
          </div>
          <button class="button button-primary" data-action="addAppointment">＋ ${t("addAppointment")}</button>
        </div>
        <div class="dashboard-appointments-list">
          ${upcoming.length ? upcoming.map((item) => `
            <div class="appointment dashboard-appointment">
              <div class="appointment-time-badge">
                <span class="time-clock">🕒</span>
                <bdi dir="ltr">${esc(item.startTime || "--:--")}</bdi>
              </div>
              <div class="appointment-body">
                <b class="appointment-patient-name">${esc(item.patientName)}</b>
                <div class="appointment-meta muted">
                  <span>🩺 ${esc(item.procedure || "Clinical visit")}</span>
                </div>
              </div>
              <div class="appointment-status">
                ${_appointmentStatusBadge(item.status)}
              </div>
              <div class="appointment-actions">
                <button class="button button-ghost button-sm" data-edit-appointment="${item.id}">${t("edit")}</button>
                <button class="appointment-delete" data-delete-appointment="${item.id}" title="${t("deleteAppointment")}" aria-label="${t("deleteAppointment")}">×</button>
              </div>
            </div>`).join("") : `
            <div class="dashboard-empty-state">
              <span class="empty-state-icon">📅</span>
              <p class="muted">${t("noVisits")}</p>
              <button class="button button-ghost" data-action="addAppointment" style="margin-top:10px;">＋ ${t("addAppointment")}</button>
            </div>`}
        </div>
      </section>

      <div class="dashboard-side-column">
        <section class="card dashboard-card">
          <div class="card-heading">
            <div class="card-title-group">
              <span class="card-heading-icon">👥</span>
              <h2>${t("patients")}</h2>
            </div>
            <button class="button button-ghost" data-view="patients">${t("viewAll") || t("patients")}</button>
          </div>
          <div class="dashboard-patients-list">
            ${state.patients.slice(0, 5).length ? state.patients.slice(0, 5).map(patientRow).join("") : `
              <div class="dashboard-empty-state">
                <span class="empty-state-icon">👥</span>
                <p class="muted">${t("noPatients")}</p>
              </div>`}
          </div>
        </section>

        ${renderKeyboardShortcutsCard()}
      </div>
    </div>`;
}

async function loadOnlineSettings() {
  if (!window.AERODENT_ONLINE || !hasPermission("clinic_settings.read")) return;
  try {
    const response = await window.AERODENT_API.get("/api/settings");
    const d = response.data;
    state.settings = {
      ...state.settings,
      clinicName: d.name,
      phone: d.phone,
      address: d.address,
      currencySymbol: d.currency || "SYR",
      workStartHour: d.work_start,
      workEndHour: d.work_end,
      slotDuration: d.slot_duration,
      inventoryExpiryWarningDays: d.inventory_expiry_warning_days,
    };
  } catch (error) {
    // Graceful error handling
  }
}

async function loadOnlineDoctors() {
  if (!window.AERODENT_ONLINE) return;
  try {
    const response = await window.AERODENT_API.get("/api/doctors");
    state.doctors = response.data || [];
  } catch (error) {
    state.doctors = [];
  }
}

async function loadOnlineStaff() {
  if (!window.AERODENT_ONLINE || !hasPermission("staff.read")) return;
  try {
    const response = await window.AERODENT_API.get("/api/staff");
    state.staff = response.data || [];
  } catch (error) {
    state.staff = [];
  }
}

function renderSettings() {
  if (window.AERODENT_ONLINE) {
    const s = state.settings;
    const canReadClinic = hasPermission("clinic_settings.read");
    const canEditClinic = hasPermission("clinic_settings.update");
    const canManageStaff = hasPermission("staff.read");

    const securityCard = `
      <div class="card">
        <div class="card-heading">
          <h2>🔒 ${t("security")}</h2>
        </div>
        <p class="muted" style="margin-bottom:14px;font-size:13px;">${t("changePasswordSubtitle")}</p>
        <form id="changePasswordForm" class="form-grid">
          <div class="field full-span">
            <label>${t("currentPassword")}</label>
            <input type="password" name="current_password" required autocomplete="current-password" placeholder="••••••••">
          </div>
          <div class="field">
            <label>${t("newPassword")}</label>
            <input type="password" name="new_password" required minlength="8" autocomplete="new-password" placeholder="••••••••">
          </div>
          <div class="field">
            <label>${t("confirmNewPassword")}</label>
            <input type="password" name="confirm_password" required minlength="8" autocomplete="new-password" placeholder="••••••••">
          </div>
          <div class="form-actions full-span" style="justify-content:flex-start;">
            <button class="button button-primary" type="submit">🔑 ${t("changePassword")}</button>
          </div>
        </form>
      </div>`;

    if (!canReadClinic) {
      return `<section class="content-grid">${securityCard}</section>`;
    }

    const clinicForm = `
      <div class="card">
        <div class="card-heading">
          <h2>${t("clinic")}</h2>
        </div>
        <form id="onlineSettingsForm" class="form-grid">
          <div class="field">
            <label>${t("clinic")}</label>
            <input name="name" value="${esc(s.clinicName || "")}" ${!canEditClinic ? "disabled" : ""} required>
          </div>
          <div class="field">
            <label>${t("phone")}</label>
            <input name="phone" value="${esc(s.phone || "")}" ${!canEditClinic ? "disabled" : ""}>
          </div>
          <div class="field full-span">
            <label>${t("address")}</label>
            <input name="address" value="${esc(s.address || "")}" ${!canEditClinic ? "disabled" : ""}>
          </div>
          <div class="field">
            <label>${t("currency")}</label>
            <select name="currency" ${!canEditClinic ? "disabled" : ""}>
              <option value="SYR" ${s.currencySymbol === "SYR" ? "selected" : ""}>SYR</option>
              <option value="USD" ${s.currencySymbol === "USD" ? "selected" : ""}>USD</option>
              <option value="EUR" ${s.currencySymbol === "EUR" ? "selected" : ""}>EUR</option>
            </select>
          </div>
          <div class="field">
            <label>${t("slot")}</label>
            <select name="slot_duration" ${!canEditClinic ? "disabled" : ""}>
              <option value="15" ${String(s.slotDuration) === "15" ? "selected" : ""}>15</option>
              <option value="30" ${String(s.slotDuration) === "30" ? "selected" : ""}>30</option>
              <option value="60" ${String(s.slotDuration) === "60" ? "selected" : ""}>60</option>
            </select>
          </div>
          <div class="field">
            <label>${t("start")}</label>
            <input type="time" name="work_start" value="${esc(s.workStartHour || "09:00")}" ${!canEditClinic ? "disabled" : ""}>
          </div>
          <div class="field">
            <label>${t("end")}</label>
            <input type="time" name="work_end" value="${esc(s.workEndHour || "18:00")}" ${!canEditClinic ? "disabled" : ""}>
          </div>
          <div class="field">
            <label>${t("invExpiryWarningDays")}</label>
            <input type="number" name="inventory_expiry_warning_days" min="1" max="365" step="1" value="${esc(s.inventoryExpiryWarningDays || 60)}" ${!canEditClinic ? "disabled" : ""}>
          </div>
          ${canEditClinic ? `<div class="form-actions full-span"><button class="button button-primary" type="submit">${t("save")}</button></div>` : ""}
        </form>
      </div>`;

    const backupCard = `
      <div class="card">
        <div class="card-heading">
          <h2>${t("backup")}</h2>
        </div>
        <p class="muted">${t("exportClinicData")}</p>
        <div class="form-actions" style="justify-content:flex-start">
          <button class="button button-primary" data-action="export">${t("serverExport")}</button>
        </div>
      </div>`;

    let staffCard = "";
    if (canManageStaff) {
      const staffList = (state.staff || []).map((user) => {
        const isSelf = user.id === state.auth?.user?.id;
        const roleLabel = user.role === "head_doctor" ? t("headDoctor") : user.role === "doctor" ? t("doctorRole") : t("secretaryRole");
        const statusLabel = user.is_active ? `<span class="badge badge-green">${t("active")}</span>` : `<span class="badge badge-gray">${t("inactive")}</span>`;
        const actions = [];
        if (!isSelf) {
          actions.push(`<button type="button" class="button button-ghost" data-toggle-staff-active="${user.id}" data-active="${user.is_active}">${user.is_active ? t("deactivate") : t("activate")}</button>`);
          actions.push(`<button type="button" class="button button-ghost" data-edit-staff="${user.id}">${t("edit")}</button>`);
          actions.push(`<button type="button" class="button btn-danger-ghost" data-delete-staff="${user.id}" title="${t("delete")}" aria-label="${t("delete")}">×</button>`);
        }
        return `<tr>
          <td>${esc(user.name)}</td>
          <td>${esc(user.email)}</td>
          <td>${esc(roleLabel)}</td>
          <td>${statusLabel}</td>
          <td>${actions.join(" ")}</td>
        </tr>`;
      }).join("");

      staffCard = `
        <div class="card full-span" style="grid-column: 1 / -1;">
          <div class="card-heading">
            <h2>${t("staff")}</h2>
            <button class="button button-primary" data-action="addStaff">＋ ${t("addStaff")}</button>
          </div>
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>${t("name")}</th>
                  <th>${t("email")}</th>
                  <th>${t("role")}</th>
                  <th>${t("status")}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                ${staffList || `<tr><td colspan="5" class="muted">${t("noPatients")}</td></tr>`}
              </tbody>
            </table>
          </div>
        </div>`;
    }

    return `<section class="content-grid">${clinicForm}${securityCard}${backupCard}${staffCard}</section>`;
  }

  const s = state.settings;
  const clinicName = s.clinicName || "";
  const doctorName = s.doctorName || "";
  const phone = s.phone || "";
  const address = s.address || "";
  const workStartHour = s.workStartHour || "09:00";
  const workEndHour = s.workEndHour || "18:00";
  const slotDuration = Number(s.slotDuration) || 30;
  return `<section class="content-grid"><div class="card"><div class="card-heading"><h2>${t("clinic")}</h2></div><form id="settingsForm" class="form-grid"><div class="field"><label>${t("clinic")}</label><input name="clinicName" value="${esc(clinicName)}"></div><div class="field"><label>${t("doctor")}</label><input name="doctorName" value="${esc(doctorName)}"></div><div class="field full-span"><label>${t("phone")}</label><input name="phone" value="${esc(phone)}"></div><div class="field full-span"><label>${t("address")}</label><input name="address" value="${esc(address)}"></div><div class="field">
  <label>${t("currency")}</label>
  <select name="currencySymbol">
    <option
      value="SYR"
      ${s.currencySymbol === "SYR" ? "selected" : ""}
    >
      SYR
    </option>
  </select>
</div><div class="field"><label>${t("slot")}</label><select name="slotDuration"><option ${String(slotDuration) === "15" ? "selected" : ""}>15</option><option ${String(slotDuration) === "30" ? "selected" : ""}>30</option><option ${String(slotDuration) === "60" ? "selected" : ""}>60</option></select></div><div class="field"><label>${t("start")}</label><input type="time" name="workStartHour" value="${esc(workStartHour)}"></div><div class="field"><label>${t("end")}</label><input type="time" name="workEndHour" value="${esc(workEndHour)}"></div><div class="form-actions full-span"><button class="button button-primary">${t("save")}</button></div></form></div><div class="card"><div class="card-heading"><h2>${t("backup")}</h2></div><p class="muted">${t("saved")}</p><div class="form-actions" style="justify-content:flex-start"><button class="button button-primary" data-action="export">${t("export")}</button><button class="button button-ghost" data-action="import">${t("import")}</button><button class="button" style="color:var(--danger);border:1px solid #fecaca" data-action="wipe">${t("wipe")}</button></div></div></section>`;
}

function addStaff() {
  if (!window.AERODENT_ONLINE || !hasPermission("staff.create")) return;
  modal(t("addStaff"), `
    <form id="addStaffForm" class="form-grid">
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
        <label>${t("role")}</label>
        <select name="role" required>
          <option value="doctor">${t("doctorRole")}</option>
          <option value="secretary">${t("secretaryRole")}</option>
          ${state.auth?.user?.role === "super_admin" ? `<option value="head_doctor">${t("headDoctor")}</option>` : ""}
        </select>
      </div>
      <div class="form-actions full-span">
        <button class="button button-primary" type="submit">${t("save")}</button>
      </div>
    </form>
  `);
  $("#addStaffForm").onsubmit = async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target));
    try {
      await window.AERODENT_API.post("/api/staff", data);
      $("#modal").classList.remove("show");
      toast(t("staffSaved"));
      await loadOnlineStaff();
      render();
    } catch (err) {
      toast(err.message || "Failed to create staff member");
    }
  };
}

function editStaff(userId) {
  if (!window.AERODENT_ONLINE || !hasPermission("staff.update")) return;
  const user = (state.staff || []).find((u) => u.id === userId);
  if (!user) return;
  modal(t("edit"), `
    <form id="editStaffForm" class="form-grid">
      <div class="field full-span">
        <label>${t("name")}</label>
        <input value="${esc(user.name)}" disabled>
      </div>
      <div class="field full-span">
        <label>${t("role")}</label>
        <select name="role">
          <option value="doctor" ${user.role === "doctor" ? "selected" : ""}>${t("doctorRole")}</option>
          <option value="secretary" ${user.role === "secretary" ? "selected" : ""}>${t("secretaryRole")}</option>
          <option value="head_doctor" ${user.role === "head_doctor" ? "selected" : ""}>${t("headDoctor")}</option>
        </select>
      </div>
      <div class="field full-span">
        <label>${t("password")} (${t("optional") || "leave blank to keep unchanged"})</label>
        <input name="password" type="password" minlength="8" placeholder="••••••••">
      </div>
      <div class="form-actions full-span">
        <button class="button button-primary" type="submit">${t("save")}</button>
      </div>
    </form>
  `);
  $("#editStaffForm").onsubmit = async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target));
    const payload = { role: data.role };
    if (data.password && data.password.trim()) {
      payload.password = data.password.trim();
    }
    try {
      await window.AERODENT_API.patch(`/api/staff/${userId}`, payload);
      $("#modal").classList.remove("show");
      toast(t("staffSaved"));
      await loadOnlineStaff();
      render();
    } catch (err) {
      toast(err.message || "Failed to update staff member");
    }
  };
}

async function toggleStaffActive(userId, currentActive) {
  if (!window.AERODENT_ONLINE || !hasPermission("staff.update")) return;
  try {
    await window.AERODENT_API.patch(`/api/staff/${userId}`, { is_active: !currentActive });
    toast(t("staffSaved"));
    await loadOnlineStaff();
    render();
  } catch (err) {
    toast(err.message || "Failed to update staff status");
  }
}

async function deleteStaff(userId) {
  if (!window.AERODENT_ONLINE || !hasPermission("staff.delete")) return;
  if (!confirm(t("confirmDeleteStaff"))) return;
  try {
    await window.AERODENT_API.delete(`/api/staff/${userId}`);
    toast(t("staffDeleted"));
    await loadOnlineStaff();
    render();
  } catch (err) {
    toast(err.message || "Failed to delete staff member");
  }
}

async function actions(action) {
  if (window.AERODENT_DEMO && action === "newPatient") {
    toast(t("demoOnePatient"));
    return;
  }
  if (
    window.AERODENT_DEMO &&
    ["export", "import", "wipe"].includes(action)
  ) {
    toast(t("featureDisabledInDemo"));
    return;
  }
  if (window.AERODENT_ONLINE && ["import", "wipe"].includes(action)) {
    toast(t("offlineOnlyAction"));
    return;
  }
  if (action === "newPatient") return newPatient();
  if (action === "addAppointment") return addAppointment();
  if (action === "addTreatment") return addTreatment();
  if (action === "addTreatmentPlan") return addTreatmentPlan();
  if (action === "addPrescription") return addPrescription();
  if (action === "addInvoice") return addInvoice();
  if (action === "addStaff") return addStaff();
  if (action === "adminCreateClinic") return adminOpenCreateClinicModal();
  if (action === "adminCreateUser") return adminOpenCreateUserModal();
  if (action === "export") return exportData();
  if (action === "import") return $("#importInput").click();
  if (action === "wipe") {
    if (prompt(t("confirmWipe")) === "WIPE") {
      const currentSettings = {
        ...state.settings,
      };

      for (const store of STORES) {
        if (store !== "settings") {
          await dbClear(store);
        }
      }

      await dbPut("settings", {
        ...currentSettings,
        id: 1,
      });

      state.selectedPatient = null;

      await refresh();
    }
  }
}

function newPatient() {
  const clinicalAllowed = !window.AERODENT_ONLINE || (typeof onlinePatientClinicalFieldsAllowed === "function" ? onlinePatientClinicalFieldsAllowed() : true);
  modal(
    t("newPatient"),
    `<form id="newPatientForm" class="form-grid">
      <div class="field full-span"><label>${t("patient")}</label><input name="name" required autofocus></div>
      <div class="field"><label>${t("phone")}</label><input name="phone"></div>
      <div class="field"><label>${t("location")}</label><input name="location"></div>
      <div class="field"><label>${t("workStudy")}</label><input name="workStudy"></div>
      <div class="field"><label>${t("dob")}</label><input type="date" name="dob"></div>
      <div class="field"><label>${t("gender")}</label><select name="gender"><option value="Female">${t("female")}</option><option value="Male">${t("male")}</option></select></div>
      ${clinicalAllowed ? `<div class="field full-span"><label>${t("allergies")}</label><input name="allergies"></div>` : ""}
      <div class="form-actions full-span"><button type="submit" class="button button-primary">${t("save")}</button></div>
    </form>`,
  );
  $("#newPatientForm").onsubmit = async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target));
    if (window.AERODENT_ONLINE) {
      const submitButton = e.target.querySelector("button[type=submit], button:not([type=button])");
      if (submitButton) submitButton.disabled = true;
      try {
        const response = await window.AERODENT_API.post("/api/patients", patientApiPayload(data));
        const createdPatient = mapApiPatient(response.data);
        state.selectedPatient = createdPatient;
        $("#modal").classList.remove("show");
        state.patientPage = 1;
        await refreshOnlinePatients();
        state.selectedPatient = createdPatient;
        render();
      } catch (error) {
        toast(error.message);
      } finally {
        if (submitButton) submitButton.disabled = false;
      }
      return;
    }
    const id = await dbPut("patients", {
      ...data,
      createdAt: new Date().toISOString(),
    });
    state.selectedPatient = { ...data, id };
    $("#modal").classList.remove("show");
    await refresh();
  };
}

function updateClock() {
  const clock = $("#clock");
  const dateLabel = $("#dateLabel");

  if (!clock || !dateLabel) {
    return;
  }

  const now = new Date();

  const language = state.settings?.currentLanguage || "ar";

  clock.textContent = now.toLocaleTimeString(
    language === "ar" ? "ar-SA" : "en-US",
    {
      hour: "2-digit",
      minute: "2-digit",
    },
  );

  dateLabel.textContent = now.toLocaleDateString(
    language === "ar" ? "ar-SA" : "en-US",
    {
      weekday: "long",
      month: "short",
      day: "numeric",
      year: "numeric",
    },
  );
}

async function refreshOnlineWorkspace() {
  if (!window.AERODENT_ONLINE) return;

  if (state.auth?.user?.role === "super_admin") {
    if (!["admin_overview", "admin_clinics", "admin_users"].includes(state.view)) {
      state.view = "admin_overview";
    }
    await loadAdminMetrics();
    await loadAdminClinics();
    await loadAdminUsers();
    render();
    return;
  }

  if (hasPermission("clinic_settings.read")) {
    await loadOnlineSettings();
  }
  await loadOnlineDoctors();
  await refreshOnlinePatients(false);

  if (state.view === "dashboard") {
    await loadOnlineDashboard();
  } else if (state.view === "treatments") {
    await loadOnlineTreatments();
    await loadOnlineInvoices();
  } else if (state.view === "treatmentPlan") {
    await loadOnlineTreatmentPlans();
  } else if (state.view === "appointments") {
    await loadOnlineAppointments();
  } else if (state.view === "prescriptions") {
    await loadOnlinePrescriptions();
  } else if (state.view === "xrays") {
    await loadOnlineXrays();
  } else if (state.view === "settings") {
    if (hasPermission("staff.read")) {
      await loadOnlineStaff();
    }
  } else if (state.view === "inventory") {
    await loadInventoryView();
  }
  render();
}
window.refreshOnlineWorkspace = refreshOnlineWorkspace;

async function startApplication() {
  if (window.AERODENT_ONLINE) {
    updateClock();
    setInterval(updateClock, 1000);
    const authenticated = await initializeOnlineAuth();
    if (authenticated) {
      await refreshOnlineWorkspace();
    }
    return;
  }
  await initializeOfflineWorkspace();
}

async function initializeOfflineWorkspace() {
  try {
    if (!window.AERODENT_ONLINE) {
      await openDB();
      await seedDatabase();
    }

    await refresh();
    updateClock();
    setInterval(updateClock, 1000);
    if (!window.AERODENT_ONLINE && state.settings.pinEnabled === true) {
      lockApp();
    } else if (!window.AERODENT_ONLINE) {
      showPINSetup();
    }
  } catch (error) {
    console.error("Application startup failed:", error);
  }
}

startApplication();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("./sw.js");
