// ============================================================
//  HR-lite Module  — Staff Scheduling · Time Clock · Credentials
// ============================================================

// ──────────────── DATA LOADING ────────────────────────────

async function loadOnlineHRData() {
    if (!window.AERODENT_ONLINE) return;
    state.hrLoading = true;
    state.hrError = "";
    try {
        const role = state.auth?.user?.role;
        const isManager = role === "head_doctor" || role === "super_admin";

        const [shiftsRes, tcStatusRes, credSummaryRes] = await Promise.all([
            window.AERODENT_API.get("/api/hr/shifts"),
            window.AERODENT_API.get("/api/hr/time-clock/status"),
            window.AERODENT_API.get("/api/hr/credentials/summary"),
        ]);

        state.hrShifts = shiftsRes?.data || [];
        state.hrTimeClockStatus = tcStatusRes || { clocked_in: false, elapsed_seconds: 0, entry: null };
        state.hrCredentialsSummary = credSummaryRes || { total: 0, active: 0, expiring_soon: 0, expired: 0, needs_attention: 0 };

        const [tcRecordsRes, credRes] = await Promise.all([
            window.AERODENT_API.get("/api/hr/time-clock/records"),
            window.AERODENT_API.get("/api/hr/credentials"),
        ]);
        state.hrTimeClockRecords = tcRecordsRes?.data || [];
        state.hrCredentials = credRes?.data || [];

        if (isManager && (!state.staff || state.staff.length === 0)) {
            try {
                const staffRes = await window.AERODENT_API.get("/api/staff");
                state.staff = staffRes?.data || [];
            } catch (_) { /* ignore */ }
        }
    } catch (err) {
        state.hrError = err?.message || t("errorOccurred");
    } finally {
        state.hrLoading = false;
    }
}

// ──────────────── LIVE TIMER ────────────────────────────

let _hrTimerInterval = null;

function _startHRTimer() {
    _stopHRTimer();
    _hrTimerInterval = setInterval(() => {
        const el = document.getElementById("hrLiveTimer");
        if (!el) { _stopHRTimer(); return; }
        state.hrTimeClockStatus.elapsed_seconds = (state.hrTimeClockStatus.elapsed_seconds || 0) + 1;
        el.textContent = _formatElapsed(state.hrTimeClockStatus.elapsed_seconds);
    }, 1000);
}

function _stopHRTimer() {
    if (_hrTimerInterval) { clearInterval(_hrTimerInterval); _hrTimerInterval = null; }
}

function _formatElapsed(totalSeconds) {
    const h = Math.floor(totalSeconds / 3600);
    const m = Math.floor((totalSeconds % 3600) / 60);
    const s = totalSeconds % 60;
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

// ──────────────── RENDER HELPERS ─────────────────────────

function _credBadge(status) {
    if (status === "expired")       return `<span class="cred-badge cred-badge--expired">${t("expired")}</span>`;
    if (status === "expiring_soon") return `<span class="cred-badge cred-badge--expiring">${t("expiringSoon")}</span>`;
    return `<span class="cred-badge cred-badge--active">${t("valid")}</span>`;
}

function _shiftStatusBadge(status) {
    const cls = { scheduled: "badge-scheduled", completed: "badge-completed", absent: "badge-absent", leave: "badge-leave" };
    const label = t("hrShiftStatus_" + status) || status;
    return `<span class="shift-badge ${cls[status] || ""}">${label}</span>`;
}

function _tcStatusBadge(status) {
    if (status === "clocked_in") return `<span class="tc-badge tc-badge--in">${t("clockedIn")}</span>`;
    return `<span class="tc-badge tc-badge--out">${t("clockedOut")}</span>`;
}

// ──────────────── SUB-VIEWS ───────────────────────────────

function _renderTimeClock() {
    const tc = state.hrTimeClockStatus || {};
    const records = state.hrTimeClockRecords || [];
    const isClockedIn = !!tc.clocked_in;
    const elapsed = tc.elapsed_seconds || 0;

    const punchBtn = isClockedIn
        ? `<button class="button button-danger hr-punch-btn" id="hrPunchBtn" data-action="out">⏹ ${t("punchOut")}</button>`
        : `<button class="button button-primary hr-punch-btn" id="hrPunchBtn" data-action="in">▶ ${t("punchIn")}</button>`;

    const clockInTime = tc.entry?.clock_in
        ? new Date(tc.entry.clock_in).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
        : "—";

    const rows = records.map(r => {
        const inTime  = r.clock_in  ? new Date(r.clock_in).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—";
        const outTime = r.clock_out ? new Date(r.clock_out).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—";
        const hoursDisplay = r.total_hours != null ? `${Number(r.total_hours).toFixed(2)}h` : "—";
        const day = r.clock_in ? new Date(r.clock_in).toLocaleDateString() : "—";
        return `<tr>
            <td>${r.user_name || "—"}</td>
            <td>${day}</td>
            <td>${inTime}</td>
            <td>${outTime}</td>
            <td>${hoursDisplay}</td>
            <td>${_tcStatusBadge(r.status)}</td>
        </tr>`;
    }).join("") || `<tr><td colspan="6" class="muted tc-empty">${t("noRecords")}</td></tr>`;

    return `
    <div class="hr-timeclock-wrap">
      <div class="punch-card" id="hrPunchCard">
        <div class="punch-card__icon">${isClockedIn ? "🟢" : "⚫"}</div>
        <div class="punch-card__status">${isClockedIn ? t("clockedIn") : t("clockedOut")}</div>
        ${isClockedIn ? `<div class="punch-card__timer" id="hrLiveTimer">${_formatElapsed(elapsed)}</div>` : ""}
        ${isClockedIn ? `<div class="punch-card__since">${t("since")} ${clockInTime}</div>` : ""}
        <label class="punch-notes-label">
          <span>${t("notes")}</span>
          <input type="text" id="hrPunchNotes" class="punch-notes-input" placeholder="${t("optionalNotes")}" maxlength="200">
        </label>
        ${punchBtn}
      </div>
      <div class="hr-attendance-log card">
        <div class="card-heading"><h3>📋 ${t("attendanceLog")}</h3></div>
        <div class="table-wrapper">
          <table class="hr-table">
            <thead><tr>
              <th>${t("staff")}</th><th>${t("date")}</th><th>${t("clockIn")}</th>
              <th>${t("clockOut")}</th><th>${t("totalHours")}</th><th>${t("status")}</th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>
    </div>`;
}

function _renderShifts() {
    const role = state.auth?.user?.role;
    const isManager = role === "head_doctor" || role === "super_admin";
    const shifts = state.hrShifts || [];

    const addBtn = isManager
        ? `<button class="button button-primary" id="hrAddShiftBtn">＋ ${t("scheduleShift")}</button>`
        : "";

    const rows = shifts.map(s => {
        const editDel = isManager
            ? `<button class="button button-ghost btn-xs" data-hr-edit-shift="${s.id}" title="${t("edit")}">✏️</button>
               <button class="button btn-danger-ghost btn-xs" data-hr-delete-shift="${s.id}" title="${t("delete")}">🗑</button>`
            : "";
        return `<tr>
          <td>${s.user_name}</td>
          <td>${s.date}</td>
          <td>${s.start_time} – ${s.end_time}</td>
          <td>${s.shift_type}</td>
          <td>${_shiftStatusBadge(s.status)}</td>
          <td>${s.notes || "—"}</td>
          <td class="action-cell">${editDel}</td>
        </tr>`;
    }).join("") || `<tr><td colspan="7" class="muted tc-empty">${t("noShifts")}</td></tr>`;

    return `
    <div class="hr-shifts-wrap">
      <div class="hr-filter-row">
        <label>${t("from")}: <input type="date" id="hrShiftFrom" class="hr-date-input" value="${_weekStart()}"></label>
        <label>${t("to")}: <input type="date" id="hrShiftTo" class="hr-date-input" value="${_weekEnd()}"></label>
        <button class="button button-ghost" id="hrShiftFilterBtn">🔍 ${t("filter")}</button>
        ${addBtn}
      </div>
      <div class="card">
        <div class="table-wrapper">
          <table class="hr-table">
            <thead><tr>
              <th>${t("staff")}</th><th>${t("date")}</th><th>${t("time")}</th>
              <th>${t("shiftType")}</th><th>${t("status")}</th><th>${t("notes")}</th><th></th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>
    </div>`;
}

function _renderCredentials() {
    const role = state.auth?.user?.role;
    const isManager = role === "head_doctor" || role === "super_admin";
    const creds = state.hrCredentials || [];
    const summary = state.hrCredentialsSummary || {};

    const kpiCards = `
    <div class="hr-kpi-row">
      <div class="hr-kpi-card hr-kpi--total">
        <div class="hr-kpi-number">${summary.total || 0}</div>
        <div class="hr-kpi-label">${t("totalCredentials")}</div>
      </div>
      <div class="hr-kpi-card hr-kpi--active">
        <div class="hr-kpi-number">${summary.active || 0}</div>
        <div class="hr-kpi-label">${t("active")}</div>
      </div>
      <div class="hr-kpi-card hr-kpi--expiring">
        <div class="hr-kpi-number">${summary.expiring_soon || 0}</div>
        <div class="hr-kpi-label">${t("expiringSoon")}</div>
      </div>
      <div class="hr-kpi-card hr-kpi--expired">
        <div class="hr-kpi-number">${summary.expired || 0}</div>
        <div class="hr-kpi-label">${t("expired")}</div>
      </div>
    </div>`;

    const addBtn = isManager
        ? `<button class="button button-primary" id="hrAddCredBtn">＋ ${t("addCredential")}</button>`
        : "";

    const rows = creds.map(c => {
        const editDel = isManager
            ? `<button class="button button-ghost btn-xs" data-hr-edit-cred="${c.id}" title="${t("edit")}">✏️</button>
               <button class="button btn-danger-ghost btn-xs" data-hr-delete-cred="${c.id}" title="${t("delete")}">🗑</button>`
            : "";
        const daysLabel = c.days_remaining >= 0
            ? `${c.days_remaining}d`
            : `${Math.abs(c.days_remaining)}d ${t("ago")}`;
        return `<tr>
          <td>${c.user_name}</td>
          <td>${c.title}</td>
          <td>${t("credType_" + c.credential_type) || c.credential_type}</td>
          <td>${c.credential_number || "—"}</td>
          <td>${c.issuing_authority || "—"}</td>
          <td>${c.expiry_date}</td>
          <td>${daysLabel}</td>
          <td>${_credBadge(c.computed_status)}</td>
          <td class="action-cell">${editDel}</td>
        </tr>`;
    }).join("") || `<tr><td colspan="9" class="muted tc-empty">${t("noCredentials")}</td></tr>`;

    return `
    <div class="hr-creds-wrap">
      ${kpiCards}
      <div class="card" style="margin-top:18px">
        <div class="card-heading">
          <h3>🪪 ${t("credentialsTitle")}</h3>
          ${addBtn}
        </div>
        <div class="table-wrapper">
          <table class="hr-table">
            <thead><tr>
              <th>${t("staff")}</th><th>${t("credentialTitle")}</th><th>${t("type")}</th>
              <th>${t("licenseNumber")}</th><th>${t("issuingAuthority")}</th>
              <th>${t("expiryDate")}</th><th>${t("daysRemaining")}</th><th>${t("status")}</th><th></th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>
    </div>`;
}

// ──────────────── ALERT BANNER ────────────────────────────

function _renderHRAlertBanner() {
    const summary = state.hrCredentialsSummary || {};
    const needs = (summary.expiring_soon || 0) + (summary.expired || 0);
    if (!needs) return "";
    return `<div class="hr-alert-banner">
      ⚠️ <strong>${needs} ${t("licenseAlert")}</strong>
      — ${summary.expired || 0} ${t("expired")}, ${summary.expiring_soon || 0} ${t("expiringSoon")}.
      <button class="hr-alert-link" data-hr-tab="credentials">${t("reviewNow")}</button>
    </div>`;
}

// ──────────────── MAIN RENDER ────────────────────────────

function renderHR() {
    if (state.hrLoading) {
        return `<div class="hr-container"><div class="loading-spinner">⏳ ${t("loading")}</div></div>`;
    }
    if (state.hrError) {
        return `<div class="hr-container"><div class="error-banner">${state.hrError}</div></div>`;
    }

    const tab = state.hrTab || "time_clock";
    const tabs = [
        ["time_clock",   "⏱ " + t("timeClock")],
        ["shifts",       "📅 " + t("staffScheduling")],
        ["credentials",  "🪪 " + t("credentials")],
    ];

    const tabHtml = tabs.map(([key, label]) =>
        `<button class="hr-tab${tab === key ? " hr-tab--active" : ""}" data-hr-tab="${key}">${label}</button>`
    ).join("");

    let content = "";
    if (tab === "time_clock")  content = _renderTimeClock();
    else if (tab === "shifts") content = _renderShifts();
    else                       content = _renderCredentials();

    if (tab === "time_clock" && state.hrTimeClockStatus?.clocked_in) {
        setTimeout(_startHRTimer, 50);
    } else {
        _stopHRTimer();
    }

    return `
    <div class="hr-container">
      ${_renderHRAlertBanner()}
      <div class="hr-tabs">${tabHtml}</div>
      <div class="hr-content">${content}</div>
    </div>`;
}

// ──────────────── MODALS ─────────────────────────────────

function _hrShiftModal(shift) {
    const isEdit = !!shift;
    const staffOptions = (state.staff || []).map(u =>
        `<option value="${u.id}" ${shift?.user_id === u.id ? "selected" : ""}>${u.name} (${u.role})</option>`
    ).join("");
    return `
    <h2>${isEdit ? t("editShift") : t("scheduleShift")}</h2>
    <form id="hrShiftForm" class="form-grid">
      <input type="hidden" name="shift_id" value="${shift?.id || ""}">
      <div class="field full-span">
        <label>${t("staff")}</label>
        <select name="user_id" required>${staffOptions}</select>
      </div>
      <div class="field">
        <label>${t("date")}</label>
        <input type="date" name="date" value="${shift?.date || ""}" required>
      </div>
      <div class="field">
        <label>${t("startTime")}</label>
        <input type="time" name="start_time" value="${shift?.start_time || "08:00"}" required>
      </div>
      <div class="field">
        <label>${t("endTime")}</label>
        <input type="time" name="end_time" value="${shift?.end_time || "17:00"}" required>
      </div>
      <div class="field">
        <label>${t("shiftType")}</label>
        <select name="shift_type">
          <option value="regular" ${(!shift || shift?.shift_type === "regular") ? "selected" : ""}>${t("regular")}</option>
          <option value="morning" ${shift?.shift_type === "morning" ? "selected" : ""}>${t("morning")}</option>
          <option value="evening" ${shift?.shift_type === "evening" ? "selected" : ""}>${t("evening")}</option>
          <option value="on_call" ${shift?.shift_type === "on_call" ? "selected" : ""}>${t("onCall")}</option>
        </select>
      </div>
      <div class="field">
        <label>${t("status")}</label>
        <select name="status">
          <option value="scheduled" ${(!shift || shift?.status === "scheduled") ? "selected" : ""}>${t("hrShiftStatus_scheduled")}</option>
          <option value="completed" ${shift?.status === "completed" ? "selected" : ""}>${t("hrShiftStatus_completed")}</option>
          <option value="absent"    ${shift?.status === "absent"    ? "selected" : ""}>${t("hrShiftStatus_absent")}</option>
          <option value="leave"     ${shift?.status === "leave"     ? "selected" : ""}>${t("hrShiftStatus_leave")}</option>
        </select>
      </div>
      <div class="field full-span">
        <label>${t("notes")}</label>
        <input type="text" name="notes" value="${shift?.notes || ""}" maxlength="300">
      </div>
      <div class="field full-span form-actions">
        <button type="submit" class="button button-primary">${isEdit ? t("save") : t("add")}</button>
        <button type="button" class="button button-ghost" id="modalCloseBtn">${t("cancel")}</button>
      </div>
    </form>`;
}

function _hrCredentialModal(cred) {
    const isEdit = !!cred;
    const staffOptions = (state.staff || []).map(u =>
        `<option value="${u.id}" ${cred?.user_id === u.id ? "selected" : ""}>${u.name} (${u.role})</option>`
    ).join("");
    return `
    <h2>${isEdit ? t("editCredential") : t("addCredential")}</h2>
    <form id="hrCredForm" class="form-grid">
      <input type="hidden" name="cred_id" value="${cred?.id || ""}">
      <div class="field full-span">
        <label>${t("staff")}</label>
        <select name="user_id" required>${staffOptions}</select>
      </div>
      <div class="field full-span">
        <label>${t("credentialTitle")}</label>
        <input type="text" name="title" value="${cred?.title || ""}" required maxlength="200">
      </div>
      <div class="field">
        <label>${t("type")}</label>
        <select name="credential_type">
          <option value="license"       ${(!cred || cred?.credential_type === "license")       ? "selected" : ""}>${t("credType_license")}</option>
          <option value="certification" ${cred?.credential_type === "certification" ? "selected" : ""}>${t("credType_certification")}</option>
          <option value="insurance"     ${cred?.credential_type === "insurance"     ? "selected" : ""}>${t("credType_insurance")}</option>
          <option value="registration"  ${cred?.credential_type === "registration"  ? "selected" : ""}>${t("credType_registration")}</option>
          <option value="other"         ${cred?.credential_type === "other"         ? "selected" : ""}>${t("credType_other")}</option>
        </select>
      </div>
      <div class="field">
        <label>${t("licenseNumber")}</label>
        <input type="text" name="credential_number" value="${cred?.credential_number || ""}" maxlength="100">
      </div>
      <div class="field">
        <label>${t("issuingAuthority")}</label>
        <input type="text" name="issuing_authority" value="${cred?.issuing_authority || ""}" maxlength="200">
      </div>
      <div class="field">
        <label>${t("issueDate")}</label>
        <input type="date" name="issue_date" value="${cred?.issue_date || ""}">
      </div>
      <div class="field">
        <label>${t("expiryDate")}</label>
        <input type="date" name="expiry_date" value="${cred?.expiry_date || ""}" required>
      </div>
      <div class="field full-span">
        <label>${t("notes")}</label>
        <input type="text" name="notes" value="${cred?.notes || ""}" maxlength="300">
      </div>
      <div class="field full-span form-actions">
        <button type="submit" class="button button-primary">${isEdit ? t("save") : t("add")}</button>
        <button type="button" class="button button-ghost" id="modalCloseBtn">${t("cancel")}</button>
      </div>
    </form>`;
}

// ──────────────── UTILITY ────────────────────────────────

function _weekStart() {
    const d = new Date();
    const day = d.getDay();
    d.setDate(d.getDate() - day + (day === 0 ? -6 : 1));
    return d.toISOString().slice(0, 10);
}

function _weekEnd() {
    const d = new Date();
    const day = d.getDay();
    d.setDate(d.getDate() - day + (day === 0 ? 0 : 7));
    return d.toISOString().slice(0, 10);
}
