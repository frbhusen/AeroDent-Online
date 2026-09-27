let onlineAppointmentRequest = 0;

function mapApiAppointment(item) {
    const patient = state.patients.find((p) => p.id === item.patient_id);
    const doctor = (state.doctorsList || []).find((d) => d.id === item.doctor_id);
    return {
        ...item,
        clinicId: item.clinic_id,
        patientId: item.patient_id,
        patientName: item.patient_name || (patient ? patient.name : `Patient #${item.patient_id}`),
        patientPhone: item.patient_phone ?? (patient ? patient.phone : null),
        doctorId: item.doctor_id,
        doctorName: item.doctor_name || (doctor ? doctor.name : ""),
        startTime: item.start_time,
        duration: item.duration,
        status: item.status || "booked",
        procedure: item.procedure || "",
        notes: item.notes || "",
        date: item.date,
        createdBy: item.created_by,
        createdAt: item.created_at,
        updatedAt: item.updated_at,
    };
}

async function loadOnlineDoctors() {
    if (!window.AERODENT_ONLINE) return;
    try {
        const response = await window.AERODENT_API.get("/api/doctors");
        state.doctorsList = response.data || [];
        state.doctors = state.doctorsList;
    } catch {
        state.doctorsList = [];
        state.doctors = [];
    }
}

async function loadOnlineWaitlist() {
    if (!window.AERODENT_ONLINE) return;
    try {
        const response = await window.AERODENT_API.get("/api/waitlist?status=waiting");
        state.waitlist = response.data || [];
    } catch {
        state.waitlist = [];
    }
}

async function loadOnlineAppointments() {
    if (!window.AERODENT_ONLINE) return;
    const requestId = ++onlineAppointmentRequest;
    state.appointmentLoading = true;
    state.appointmentError = "";
    render();

    const weekDates = calendarWeekDates(state.agendaDate);
    const startDate = weekDates[0];
    const endDate = weekDates[weekDates.length - 1];

    try {
        const [apptRes] = await Promise.all([
            window.AERODENT_API.get(
                `/api/appointments?start_date=${startDate}&end_date=${endDate}&per_page=100`
            ),
            loadOnlineWaitlist(),
        ]);
        if (requestId !== onlineAppointmentRequest) return;

        let allAppointments = apptRes.data || [];
        const totalPages = apptRes.meta && apptRes.meta.pages ? apptRes.meta.pages : 1;
        for (let page = 2; page <= totalPages; page += 1) {
            const nextRes = await window.AERODENT_API.get(
                `/api/appointments?start_date=${startDate}&end_date=${endDate}&per_page=100&page=${page}`
            );
            if (requestId !== onlineAppointmentRequest) return;
            allAppointments = allAppointments.concat(nextRes.data || []);
        }

        state.appointments = allAppointments.map(mapApiAppointment);
    } catch (error) {
        if (requestId !== onlineAppointmentRequest) return;
        state.appointmentError = error.message;
    } finally {
        if (requestId === onlineAppointmentRequest) {
            state.appointmentLoading = false;
            render();
        }
    }
}

function renderAppointments() {
    const entries = state.appointments.filter(
        (item) => item.date === state.agendaDate,
    );

    const workStart = state.settings.work_start || state.settings.workStartHour || "09:00";
    const workEnd = state.settings.work_end || state.settings.workEndHour || "18:00";
    const slotDuration = Number(state.settings.slot_duration || state.settings.slotDuration) || 15;

    const start = timeToMinutes(workStart);
    const end = timeToMinutes(workEnd);
    const slot = slotDuration;

    const times = [];
    for (let value = start; value < end; value += slot) {
        times.push(minutesToTime(value));
    }

    const positionedEntries = layoutAgendaEntries(entries, start, end, slot, times.length);

    const weekDates = calendarWeekDates(state.agendaDate);
    const weekStrip = weekDates
        .map(
            (date) =>
                `<button class="calendar-day ${date === state.agendaDate ? "active" : ""}" data-agenda-date="${date}" data-day-target="${date}">
                    <span>${calendarDateLabel(date)}</span>
                    <b>${state.appointments.filter((item) => item.date === date).length}</b>
                </button>`
        )
        .join("");

    const activeWaitlistCount = (state.waitlist || []).filter(w => w.status === "waiting").length;

    return `
        <section class="card calendar-card">
            <div class="card-heading">
                <div>
                    <h2>${t("appointments")}</h2>
                    <div class="agenda-date-controls">
                        <button
                            class="icon-button"
                            data-agenda-date="previous"
                            title="${t("previousDay")}"
                            aria-label="${t("previousDay")}"
                        >‹</button>
                        <button
                            class="button button-ghost"
                            data-agenda-date="today"
                        >${t("today")}</button>
                        <b>${calendarDateLabel(state.agendaDate)}</b>
                        <button
                            class="icon-button"
                            data-agenda-date="next"
                            title="${t("nextDay")}"
                            aria-label="${t("nextDay")}"
                        >›</button>
                    </div>
                </div>
                <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                    <button class="button ${state.showWaitlistPanel ? 'button-primary' : 'button-ghost'}" id="toggleWaitlistBtn">
                        📋 ${t("waitlist")} <span class="badge ${activeWaitlistCount > 0 ? 'badge-urgent' : ''}" style="margin-inline-start:4px;">${activeWaitlistCount}</span>
                    </button>
                    <button class="button button-primary" data-action="addAppointment">
                        ＋ ${t("addAppointment")}
                    </button>
                </div>
            </div>

            ${state.showWaitlistPanel ? renderWaitlistPanel() : ""}

            <div class="calendar-week">
                ${weekStrip}
            </div>

            <div class="calendar-summary">
                <strong>${entries.length}</strong>
                <span>${t("appointments")} · ${state.agendaDate}</span>
                ${state.appointmentLoading ? `<span class="muted" style="margin-inline-start:12px;">${t("loading")}</span>` : ""}
            </div>

            ${state.appointmentError ? `<div class="alert-banner" style="margin:12px;">${esc(state.appointmentError)}</div>` : ""}

            <div class="agenda" style="grid-template-rows: repeat(${times.length}, var(--agenda-row-h, 44px));">
                ${times.map((time, index) => `
                    <div class="agenda-row agenda-slot-target" data-slot-time="${time}" style="grid-row: ${index + 1};">
                        <div class="agenda-time">${time}</div>
                        <div class="agenda-slot-content"></div>
                    </div>
                `).join("")}
                ${positionedEntries.map((item) => `
                    <div class="appointment status-${item.status || 'booked'} ${item.status === 'cancelled' ? 'is-cancelled' : ''}"
                         draggable="true"
                         data-appointment-id="${item.id}"
                         title="${t("dragToReschedule")}"
                         style="grid-column: 2; grid-row: ${item._rowStart + 1} / span ${item._rowSpan}; width: calc(${item._widthPct}% - 4px); margin-inline-start: ${item._leftPct}%;">
                        <div style="cursor: grab;">
                            <b>${esc(item.patientName)} · ${esc(item.procedure || "Visit")}</b>
                            <span class="muted" style="display:flex;align-items:center;gap:6px;margin-top:2px;">
                                <span>⏰ ${esc(item.startTime)} (${item.duration || 30}m)</span>
                                ${item.doctorName ? `<span>· 👨‍⚕️ ${esc(item.doctorName)}</span>` : ""}
                            </span>
                        </div>
                        <div style="display:flex;gap:6px;align-items:center;" data-stop-propagation>
                            <select class="appointment-status-select" data-update-appt-status="${item.id}">
                                <option value="booked" ${item.status === "booked" ? "selected" : ""}>📅 ${t("statusBooked")}</option>
                                <option value="arrived" ${item.status === "arrived" ? "selected" : ""}>🚶 ${t("statusArrived")}</option>
                                <option value="in_chair" ${item.status === "in_chair" ? "selected" : ""}>🦷 ${t("statusInChair")}</option>
                                <option value="completed" ${item.status === "completed" ? "selected" : ""}>✓ ${t("statusCompleted")}</option>
                                <option value="cancelled" ${item.status === "cancelled" ? "selected" : ""}>✕ ${t("statusCancelled")}</option>
                            </select>
                            ${typeof appointmentWhatsappButton === "function" ? appointmentWhatsappButton(item) : ""}
                            <button class="button button-ghost button-sm" data-edit-appointment="${item.id}">${t("edit")}</button>
                            <button
                                class="appointment-delete"
                                data-delete-appointment="${item.id}"
                                title="${t("deleteAppointment")}"
                                aria-label="${t("deleteAppointment")}"
                            >×</button>
                        </div>
                    </div>
                `).join("")}
            </div>
        </section>
    `;
}

async function addAppointment() {
    if (window.AERODENT_ONLINE && (!state.doctorsList || !state.doctorsList.length)) {
        await loadOnlineDoctors();
    }
    if (window.AERODENT_ONLINE && (!state.patients || !state.patients.length)) {
        if (typeof refreshOnlinePatients === "function") await refreshOnlinePatients();
    }

    const patientOptions = state.patients
        .map(
            (patient) =>
                `<option value="${patient.id}" ${patient.id === state.selectedPatient?.id ? "selected" : ""}>
                    ${esc(patient.name)} · ${esc(patient.phone || "")}
                </option>`
        )
        .join("");

    const isSecretary = window.AERODENT_ONLINE && state.auth.user?.role === "secretary";
    const doctorField = isSecretary && state.doctorsList?.length
        ? `<div class="field">
            <label>${t("doctor")}</label>
            <select name="doctorId">
                <option value="">${t("selectDoctor") || "Select Doctor"}</option>
                ${state.doctorsList.map((doc) => `<option value="${doc.id}">${esc(doc.name)}</option>`).join("")}
            </select>
        </div>`
        : "";

    const defaultDuration = state.settings.slot_duration || state.settings.slotDuration || 30;

    modal(
        t("addAppointment"),
        `<form id="appointmentForm" class="form-grid">
            <div class="field full-span">
                <label>${t("patient")}</label>
                <select name="patientId" required>
                    <option value="">${t("selectPatient")}</option>
                    ${patientOptions}
                </select>
            </div>
            ${doctorField}
            <div class="field">
                <label>${t("date")}</label>
                <input type="date" name="date" required value="${state.agendaDate}">
            </div>
            <div class="field">
                <label>${t("time")}</label>
                <input type="time" name="startTime" required value="10:00">
            </div>
            <div class="field">
                <label>${t("slot")}</label>
                <input type="number" name="duration" min="5" max="240" value="${defaultDuration}">
            </div>
            <div class="field">
                <label>${t("status")}</label>
                <select name="status">
                    <option value="booked" selected>${t("booked")}</option>
                    <option value="completed">${t("completed")}</option>
                    <option value="cancelled">${t("cancelled")}</option>
                </select>
            </div>
            <div class="field full-span">
                <label>${t("procedure")}</label>
                <input name="procedure" placeholder="e.g. Consultation, Cleaning" required>
            </div>
            <div class="field full-span">
                <label>${t("notes")}</label>
                <textarea name="notes" rows="2"></textarea>
            </div>
            <div class="form-actions full-span">
                <button class="button button-primary" type="submit">${t("save")}</button>
            </div>
        </form>`
    );

    $("#appointmentForm").onsubmit = async (event) => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(event.target));

        if (window.AERODENT_ONLINE) {
            if (state.appointmentSaving) return;
            state.appointmentSaving = true;
            try {
                const payload = {
                    patient_id: Number(data.patientId),
                    doctor_id: data.doctorId ? Number(data.doctorId) : undefined,
                    date: data.date,
                    start_time: data.startTime,
                    duration: Number(data.duration) || 30,
                    status: data.status || "booked",
                    procedure: data.procedure,
                    notes: data.notes || "",
                };
                await window.AERODENT_API.post("/api/appointments", payload);
                $("#modal").classList.remove("show");
                state.agendaDate = data.date;
                if (state.view === "dashboard" && typeof loadOnlineDashboard === "function") {
                    await loadOnlineDashboard();
                }
                await loadOnlineAppointments();
                render();
                toast(t("savedOnline"));
            } catch (error) {
                toast(error.message || "Failed to schedule appointment.");
            } finally {
                state.appointmentSaving = false;
            }
            return;
        }

        const patient = state.patients.find((item) => item.id === Number(data.patientId));
        if (!patient) {
            toast(t("selectPatient"));
            return;
        }

        await dbPut("appointments", {
            ...data,
            patientId: patient.id,
            patientName: patient.name,
            duration: Number(data.duration) || 30,
        });

        $("#modal").classList.remove("show");
        state.agendaDate = data.date;
        await refresh();
    };
}

async function editAppointment(id) {
    let appointment = state.appointments.find((item) => item.id === id);
    if (!appointment && state.dashboard?.upcoming_appointments) {
        const raw = state.dashboard.upcoming_appointments.find((item) => item.id === id);
        if (raw) appointment = mapApiAppointment(raw);
    }
    if (!appointment && window.AERODENT_ONLINE) {
        try {
            const response = await window.AERODENT_API.get(`/api/appointments/${id}`);
            if (response.data) appointment = mapApiAppointment(response.data);
        } catch (error) {
            console.error("Failed to fetch appointment:", error);
        }
    }
    if (!appointment) return;

    const timeValue = appointment.startTime || appointment.start_time || "10:00";

    modal(
        t("edit"),
        `<form id="editAppointmentForm" class="form-grid">
            <div class="field">
                <label>${t("date")}</label>
                <input type="date" name="date" required value="${appointment.date}">
            </div>
            <div class="field">
                <label>${t("time")}</label>
                <input type="time" name="startTime" required value="${timeValue}">
            </div>
            <div class="field">
                <label>${t("slot")}</label>
                <input type="number" name="duration" min="5" max="240" value="${appointment.duration || 30}">
            </div>
            <div class="field">
                <label>${t("status")}</label>
                <select name="status">
                    <option value="booked" ${appointment.status === "booked" ? "selected" : ""}>${t("booked")}</option>
                    <option value="arrived" ${appointment.status === "arrived" ? "selected" : ""}>${t("arrived")}</option>
                    <option value="in_chair" ${appointment.status === "chair" || appointment.status === "in_chair" ? "selected" : ""}>${t("chair")}</option>
                    <option value="completed" ${appointment.status === "completed" ? "selected" : ""}>${t("completed")}</option>
                    <option value="cancelled" ${appointment.status === "cancelled" ? "selected" : ""}>${t("cancelled")}</option>
                </select>
            </div>
            <div class="field full-span">
                <label>${t("procedure")}</label>
                <input name="procedure" required value="${esc(appointment.procedure || "")}">
            </div>
            <div class="field full-span">
                <label>${t("notes")}</label>
                <textarea name="notes" rows="2">${esc(appointment.notes || "")}</textarea>
            </div>
            <div class="form-actions full-span">
                <button class="button button-primary" type="submit">${t("save")}</button>
            </div>
        </form>`
    );

    $("#editAppointmentForm").onsubmit = async (event) => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(event.target));

        if (window.AERODENT_ONLINE) {
            if (state.appointmentSaving) return;
            state.appointmentSaving = true;
            try {
                const payload = {
                    date: data.date,
                    start_time: data.startTime,
                    duration: Number(data.duration) || 30,
                    status: data.status,
                    procedure: data.procedure,
                    notes: data.notes || "",
                };
                const response = await window.AERODENT_API.patch(`/api/appointments/${appointment.id}`, payload);
                const updated = mapApiAppointment(response.data);
                const index = state.appointments.findIndex((item) => item.id === appointment.id);
                if (index !== -1) {
                    state.appointments[index] = updated;
                }
                if (state.dashboard?.upcoming_appointments) {
                    const dIndex = state.dashboard.upcoming_appointments.findIndex((item) => item.id === appointment.id);
                    if (dIndex !== -1) {
                        state.dashboard.upcoming_appointments[dIndex] = {
                            ...state.dashboard.upcoming_appointments[dIndex],
                            date: updated.date,
                            start_time: updated.startTime,
                            duration: updated.duration,
                            procedure: updated.procedure,
                            status: updated.status,
                        };
                    }
                }
                $("#modal").classList.remove("show");
                state.agendaDate = data.date;
                if (state.view === "dashboard" && typeof loadOnlineDashboard === "function") {
                    await loadOnlineDashboard();
                }
                if (typeof loadOnlineAppointments === "function") {
                    await loadOnlineAppointments();
                }
                render();
                toast(t("savedOnline"));
                if (data.status === "cancelled" && typeof promptWaitlistAutoFill === "function") {
                    promptWaitlistAutoFill(updated);
                }
            } catch (error) {
                toast(error.message || "Failed to update appointment.");
            } finally {
                state.appointmentSaving = false;
            }
            return;
        }

        await dbPut("appointments", { ...appointment, ...data, duration: Number(data.duration) || 30 });
        $("#modal").classList.remove("show");
        await refresh();
    };
}

async function deleteAppointment(id) {
    let appointment = state.appointments.find((item) => item.id === id);
    if (!appointment && state.dashboard?.upcoming_appointments) {
        const raw = state.dashboard.upcoming_appointments.find((item) => item.id === id);
        if (raw) appointment = mapApiAppointment(raw);
    }
    if (!appointment && window.AERODENT_ONLINE) {
        try {
            const response = await window.AERODENT_API.get(`/api/appointments/${id}`);
            if (response.data) appointment = mapApiAppointment(response.data);
        } catch (error) {
            console.error("Failed to fetch appointment:", error);
        }
    }
    if (!appointment) return;
    if (!confirm(t("deleteAppointment") + "?")) return;

    if (window.AERODENT_ONLINE) {
        if (state.appointmentSaving) return;
        state.appointmentSaving = true;
        try {
            await window.AERODENT_API.delete(`/api/appointments/${id}`);
            state.appointments = state.appointments.filter((item) => item.id !== id);
            if (state.dashboard?.upcoming_appointments) {
                state.dashboard.upcoming_appointments = state.dashboard.upcoming_appointments.filter((item) => item.id !== id);
                if (state.dashboard.upcoming_appointments_count > 0) {
                    state.dashboard.upcoming_appointments_count--;
                }
            }
            if (state.view === "dashboard" && typeof loadOnlineDashboard === "function") {
                await loadOnlineDashboard();
            }
            render();
            toast(t("savedOnline"));
        } catch (error) {
            toast(error.message || "Failed to delete appointment.");
        } finally {
            state.appointmentSaving = false;
        }
        return;
    }

    await dbDelete("appointments", id);
    await refresh();
    showUndo(t("deleteAppointment"), async () => {
        await dbPut("appointments", appointment);
        await refresh();
    });
}

function layoutAgendaEntries(entries, dayStart, dayEnd, rowMinutes, totalRows) {
    const items = entries
        .map((item) => {
            const itemStart = timeToMinutes(item.startTime);
            const duration = Number(item.duration) > 0 ? Number(item.duration) : rowMinutes;
            return { ...item, _start: itemStart, _end: itemStart + duration };
        })
        .filter((item) => item._start < dayEnd && item._end > dayStart)
        .sort((a, b) => a._start - b._start || a._end - b._end);

    const clusters = [];
    let current = [];
    let currentEnd = -Infinity;
    for (const item of items) {
        if (current.length && item._start >= currentEnd) {
            clusters.push(current);
            current = [];
            currentEnd = -Infinity;
        }
        current.push(item);
        currentEnd = Math.max(currentEnd, item._end);
    }
    if (current.length) clusters.push(current);

    const positioned = [];
    for (const cluster of clusters) {
        const columnEnds = [];
        for (const item of cluster) {
            let columnIndex = columnEnds.findIndex((end) => end <= item._start);
            if (columnIndex === -1) {
                columnIndex = columnEnds.length;
                columnEnds.push(item._end);
            } else {
                columnEnds[columnIndex] = item._end;
            }
            item._col = columnIndex;
        }
        const totalCols = columnEnds.length;
        for (const item of cluster) {
            const visibleStart = Math.max(item._start, dayStart);
            const visibleEnd = Math.min(item._end, dayEnd);
            const rowStart = Math.min(totalRows - 1, Math.floor((visibleStart - dayStart) / rowMinutes));
            const rowSpan = Math.max(1, Math.min(totalRows - rowStart, Math.round((visibleEnd - visibleStart) / rowMinutes)));
            const widthPct = 100 / totalCols;
            positioned.push({
                ...item,
                _rowStart: rowStart,
                _rowSpan: rowSpan,
                _widthPct: widthPct,
                _leftPct: item._col * widthPct,
            });
        }
    }
    return positioned;
}

function timeToMinutes(value) {
    const [hours, minutes] = String(value || "00:00").split(":").map(Number);
    return hours * 60 + minutes;
}

function minutesToTime(value) {
    return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
}

function calendarDateLabel(date) {
    return new Date(`${date}T12:00:00`).toLocaleDateString(
        currentLanguage === "ar" ? "ar-SA" : "en-US",
        {
            weekday: "short",
            day: "numeric",
            month: "short",
        }
    );
}

function calendarWeekDates(centerDate) {
    const center = new Date(`${centerDate}T12:00:00`);
    const day = center.getDay();
    const start = new Date(center);
    start.setDate(center.getDate() - day);

    return Array.from({ length: 7 }, (_, index) => {
        const date = new Date(start);
        date.setDate(start.getDate() + index);
        return date.toISOString().slice(0, 10);
    });
}

function renderWaitlistPanel() {
    const waiting = (state.waitlist || []).filter((w) => w.status === "waiting");
    return `
    <div class="waitlist-panel">
        <div class="waitlist-header">
            <div>
                <h3 style="margin:0;display:flex;align-items:center;gap:8px;">
                    📋 ${t("waitlist")}
                    <span class="badge badge-blue">${waiting.length} ${t("waiting")}</span>
                </h3>
                <small class="muted">${t("dragToReschedule")} (drag onto any slot to book)</small>
            </div>
            <button class="button button-primary button-sm" data-action="addWaitlist">
                ＋ ${t("addToWaitlist")}
            </button>
        </div>
        ${!waiting.length ? `<p class="muted" style="margin:8px 0;">${t("noWaitlistPatients")}</p>` : `
            <div class="waitlist-grid">
                ${waiting.map((item) => `
                    <div class="waitlist-card priority-${item.priority || 'normal'}" draggable="true" data-waitlist-id="${item.id}" title="${t("dragToReschedule")}">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <strong>${esc(item.patient_name || item.patientName || `Patient #${item.patient_id}`)}</strong>
                            <span class="badge badge-${item.priority || 'normal'}">${t(item.priority || 'normal')}</span>
                        </div>
                        <div class="muted" style="font-size:11px;">
                            <span>${esc(item.procedure || t("treatment"))}</span>
                            ${item.preferred_time ? ` · 🕒 ${esc(item.preferred_time)}` : ""}
                            ${item.preferred_date ? ` · 📅 ${esc(item.preferred_date)}` : ""}
                        </div>
                        ${item.patient_phone ? `<div class="muted" style="font-size:11px;">📞 ${esc(item.patient_phone)}</div>` : ""}
                        ${item.notes ? `<p style="margin:2px 0 0 0;font-size:11px;color:var(--muted);">${esc(item.notes)}</p>` : ""}
                        <div style="margin-top:6px;display:flex;justify-content:space-between;align-items:center;" data-stop-propagation>
                            <button class="button button-ghost button-sm" data-book-waitlist="${item.id}" title="${t("bookSlot")}">
                                ⚡ ${t("bookSlot")}
                            </button>
                            <button class="button button-sm" style="color:var(--danger);" data-delete-waitlist="${item.id}">
                                ×
                            </button>
                        </div>
                    </div>
                `).join("")}
            </div>
        `}
    </div>
    `;
}

async function addWaitlistEntry() {
    if (window.AERODENT_ONLINE && (!state.patients || !state.patients.length)) {
        if (typeof refreshOnlinePatients === "function") await refreshOnlinePatients();
    }

    const patientOptions = (state.patients || [])
        .map(
            (patient) =>
                `<option value="${patient.id}" ${patient.id === state.selectedPatient?.id ? "selected" : ""}>
                    ${esc(patient.name)} · ${esc(patient.phone || "")}
                </option>`
        )
        .join("");

    modal(
        `＋ ${t("addToWaitlist")}`,
        `<form id="waitlistForm" class="form-grid">
            <div class="field full-span">
                <label>${t("patient")}</label>
                <select name="patientId" required>
                    <option value="">${t("selectPatient")}</option>
                    ${patientOptions}
                </select>
            </div>
            <div class="field">
                <label>${t("priority")}</label>
                <select name="priority">
                    <option value="normal">${t("normal")}</option>
                    <option value="high">${t("high")}</option>
                    <option value="urgent">${t("urgent")}</option>
                </select>
            </div>
            <div class="field">
                <label>${t("preferredTime")}</label>
                <input name="preferredTime" placeholder="e.g. Morning, 10:00, Any">
            </div>
            <div class="field full-span">
                <label>${t("preferredDate")}</label>
                <input type="date" name="preferredDate" value="${state.agendaDate || today()}">
            </div>
            <div class="field full-span">
                <label>${t("procedure")}</label>
                <input name="procedure" placeholder="e.g. Extraction, Crown, Cleaning" required>
            </div>
            <div class="field full-span">
                <label>${t("notes")}</label>
                <textarea name="notes" rows="2"></textarea>
            </div>
            <div class="form-actions full-span">
                <button class="button button-primary" type="submit">${t("save")}</button>
            </div>
        </form>`
    );

    $("#waitlistForm").onsubmit = async (event) => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(event.target));
        if (window.AERODENT_ONLINE) {
            try {
                await window.AERODENT_API.post("/api/waitlist", {
                    patient_id: Number(data.patientId),
                    priority: data.priority || "normal",
                    preferred_time: data.preferredTime || null,
                    preferred_date: data.preferredDate || null,
                    procedure: data.procedure,
                    notes: data.notes || "",
                });
                $("#modal").classList.remove("show");
                await loadOnlineWaitlist();
                state.showWaitlistPanel = true;
                render();
                toast(t("savedOnline"));
            } catch (err) {
                toast(err.message || "Failed to add to waitlist.");
            }
        } else {
            const patient = state.patients.find((p) => p.id === Number(data.patientId));
            if (!patient) return;
            const newEntry = {
                id: Date.now(),
                patient_id: patient.id,
                patient_name: patient.name,
                patient_phone: patient.phone,
                priority: data.priority || "normal",
                preferred_time: data.preferredTime || null,
                preferred_date: data.preferredDate || null,
                procedure: data.procedure,
                status: "waiting",
                notes: data.notes || "",
            };
            state.waitlist.push(newEntry);
            $("#modal").classList.remove("show");
            state.showWaitlistPanel = true;
            render();
            toast(t("savedLocal") || "Saved locally");
        }
    };
}

async function deleteWaitlistEntry(id) {
    if (!confirm(t("delete") + "?")) return;
    if (window.AERODENT_ONLINE) {
        try {
            await window.AERODENT_API.delete(`/api/waitlist/${id}`);
            state.waitlist = (state.waitlist || []).filter((w) => w.id !== id);
            render();
            toast(t("savedOnline"));
        } catch (err) {
            toast(err.message || "Failed to delete from waitlist.");
        }
    } else {
        state.waitlist = (state.waitlist || []).filter((w) => w.id !== id);
        render();
    }
}

async function rescheduleAppointment(appointmentId, newDate, newTime) {
    const appt = state.appointments.find((a) => a.id === appointmentId);
    if (!appt) return;

    const oldDate = appt.date;
    const oldTime = appt.startTime;

    if (oldDate === newDate && oldTime === newTime) return;

    // Optimistic update
    appt.date = newDate;
    appt.startTime = newTime;
    render();

    if (window.AERODENT_ONLINE) {
        try {
            await window.AERODENT_API.patch(`/api/appointments/${appointmentId}`, {
                date: newDate,
                start_time: newTime,
            });
            toast(t("appointmentRescheduled") || `Rescheduled to ${newTime}`);
            await loadOnlineAppointments();
        } catch (error) {
            console.error("Failed to reschedule:", error);
            toast(error.message || "Failed to reschedule appointment.");
            // Revert
            appt.date = oldDate;
            appt.startTime = oldTime;
            render();
            await loadOnlineAppointments();
        }
    } else {
        await dbPut("appointments", appt);
        toast(t("appointmentRescheduled") || `Rescheduled to ${newTime}`);
        await refresh();
    }
}

async function bookWaitlistIntoSlot(waitlistId, targetDate, targetTime, doctorId) {
    if (window.AERODENT_ONLINE) {
        try {
            await window.AERODENT_API.post(`/api/waitlist/${waitlistId}/auto-fill`, {
                date: targetDate,
                start_time: targetTime,
                doctor_id: doctorId,
            });
            toast(t("slotAutoFilled") || "Slot booked from wait-list!");
            state.agendaDate = targetDate;
            await loadOnlineWaitlist();
            await loadOnlineAppointments();
            render();
        } catch (error) {
            toast(error.message || "Failed to book slot from wait-list.");
        }
    } else {
        const w = (state.waitlist || []).find((x) => x.id === waitlistId);
        if (w) {
            w.status = "booked";
            await dbPut("appointments", {
                patientId: w.patient_id,
                patientName: w.patient_name || w.patientName,
                date: targetDate,
                startTime: targetTime,
                duration: 30,
                status: "booked",
                procedure: w.procedure || "Waitlist Booking",
            });
            toast(t("slotAutoFilled") || "Slot booked from wait-list!");
            await refresh();
        }
    }
}

function promptWaitlistAutoFill(cancelledAppt) {
    const waiting = (state.waitlist || []).filter((w) => w.status === "waiting");
    if (!waiting.length) return;

    modal(
        `⚡ ${t("waitlistAutoFill")}`,
        `<div style="display:flex;flex-direction:column;gap:14px;">
            <div class="alert-banner" style="background:#eff6ff;border:1px solid #bfdbfe;color:#1e3a8a;border-radius:8px;padding:12px;">
                <strong>${t("autoFillPrompt")}</strong>
                <div style="margin-top:4px;font-size:12px;">
                    📅 <b>${esc(cancelledAppt.date)}</b> at ⏰ <b>${esc(cancelledAppt.startTime)}</b>
                    ${cancelledAppt.doctorName ? ` (👨‍⚕️ ${esc(cancelledAppt.doctorName)})` : ""}
                </div>
            </div>
            <p class="muted" style="margin:0;font-size:12px;">${waiting.length} patient(s) waiting. Choose a patient to instantly fill this vacant slot:</p>
            <div style="display:flex;flex-direction:column;gap:8px;max-height:300px;overflow-y:auto;">
                ${waiting.map((w) => `
                    <div style="border:1px solid var(--border);border-radius:8px;padding:10px 12px;display:flex;justify-content:space-between;align-items:center;background:#fff;">
                        <div>
                            <div style="display:flex;align-items:center;gap:6px;">
                                <strong>${esc(w.patient_name || w.patientName || `Patient #${w.patient_id}`)}</strong>
                                <span class="badge badge-${w.priority || 'normal'}">${t(w.priority || 'normal')}</span>
                            </div>
                            <div class="muted" style="font-size:11px;margin-top:2px;">
                                ${esc(w.procedure || 'Visit')}${w.preferred_time ? ` · Preferred: ${esc(w.preferred_time)}` : ""}
                                ${w.patient_phone ? ` · 📞 ${esc(w.patient_phone)}` : ""}
                            </div>
                        </div>
                        <button class="button button-primary button-sm" data-autofill-confirm="${w.id}">
                            ⚡ ${t("bookSlot")}
                        </button>
                    </div>
                `).join("")}
            </div>
            <div class="form-actions" style="margin-top:8px;">
                <button type="button" class="button button-ghost" data-close-modal>${t("cancel")}</button>
            </div>
        </div>`
    );

    $$("#modal [data-close-modal]").forEach((btn) => {
        btn.onclick = () => $("#modal").classList.remove("show");
    });

    $$("[data-autofill-confirm]").forEach((btn) => {
        btn.onclick = async () => {
            const waitlistId = Number(btn.dataset.autofillConfirm);
            $("#modal").classList.remove("show");
            await bookWaitlistIntoSlot(waitlistId, cancelledAppt.date, cancelledAppt.startTime, cancelledAppt.doctorId);
        };
    });
}