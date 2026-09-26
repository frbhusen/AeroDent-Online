let onlineTimelineRequest = 0;

async function loadOnlinePatientTimeline(patientId) {
    if (!window.AERODENT_ONLINE || !patientId) return;
    const requestId = ++onlineTimelineRequest;
    if (!state.onlineTimeline) {
        state.onlineTimeline = { patientId: null, events: [], loading: false, error: "" };
    }
    state.onlineTimeline.patientId = patientId;
    state.onlineTimeline.loading = true;
    state.onlineTimeline.error = "";
    
    try {
        const response = await window.AERODENT_API.get(`/api/patients/${patientId}/timeline`);
        if (requestId !== onlineTimelineRequest || state.selectedPatient?.id !== patientId) return;
        const rawEvents = Array.isArray(response.data) ? response.data : (response.data?.events || []);
        state.onlineTimeline = {
            patientId,
            events: rawEvents,
            loading: false,
            error: "",
        };
    } catch (error) {
        if (requestId !== onlineTimelineRequest || state.selectedPatient?.id !== patientId) return;
        state.onlineTimeline = {
            patientId,
            events: [],
            loading: false,
            error: error.message || "Failed to load timeline",
        };
    } finally {
        if (requestId === onlineTimelineRequest && state.selectedPatient?.id === patientId) {
            state.onlineTimeline.loading = false;
            // Only re-render if still on patients view
            if (state.view === "patients") render();
        }
    }
}

function renderPatientTimeline(patientId) {
    if (window.AERODENT_ONLINE) {
        if (!state.onlineTimeline || state.onlineTimeline.patientId !== patientId) {
            setTimeout(() => loadOnlinePatientTimeline(patientId), 0);
            return `<div class="timeline-empty"><p class="muted">${t("loading")}</p></div>`;
        }

        if (state.onlineTimeline.loading) {
            return `<div class="timeline-empty"><p class="muted">${t("loading")}</p></div>`;
        }

        if (state.onlineTimeline.error) {
            return `<div class="timeline-empty"><p class="login-error">${esc(state.onlineTimeline.error)}</p></div>`;
        }

        const events = state.onlineTimeline.events || [];
        if (!events.length) {
            return `<div class="timeline-empty">${t("noVisits")}</div>`;
        }

        return `
        <div class="patient-timeline">
            ${events.map((event) => `
                <div class="timeline-event ${event.type === "xray" ? "timeline-event-clickable" : ""}" ${event.type === "xray" ? `data-open-xray="${event.id}" title="${t("xrays")}"` : ""}>
                    <div class="timeline-marker">${event.icon || "•"}</div>
                    <div class="timeline-content">
                        <div class="timeline-event-header">
                            <div>
                                <strong>${esc(event.title)}</strong>
                                <small>${esc(event.date)}${event.time ? ` · ${esc(event.time)}` : ""}</small>
                            </div>
                            ${event.status ? `<span class="badge">${t(event.status)}</span>` : ""}
                        </div>
                        <p>${esc(event.description)}</p>
                        ${event.type === "xray" ? `
                            <div class="timeline-xray-preview" style="margin-top: 8px; display: inline-flex; align-items: center; gap: 8px;">
                                <img src="/api/x-rays/${event.id}/file" 
                                     alt="${esc(event.title)}" 
                                     style="width: 56px; height: 56px; object-fit: cover; border-radius: var(--radius-sm, 6px); border: 1px solid var(--border); box-shadow: 0 1px 3px rgba(0,0,0,0.06);" 
                                     onerror="this.style.display='none'" 
                                     loading="lazy">
                                <span class="badge" style="cursor: pointer; display: inline-flex; align-items: center; gap: 4px;">
                                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>
                                    ${t("view")}
                                </span>
                            </div>
                        ` : ""}
                    </div>
                </div>
            `).join("")}
        </div>`;
    }

    const events = [];

    // Appointments
    state.appointments
        .filter((item) => item.patientId === patientId)
        .forEach((item) => {
            events.push({
                type: "appointment",
                date: item.date || "",
                time: item.startTime || "",
                title: item.procedure || t("appointment"),
                description: `${item.startTime || ""} · ${t(item.status || "booked")}`,
                icon: "📅",
                status: item.status || "booked",
            });
        });

    // Treatments
    state.treatments
        .filter((item) => item.patientId === patientId)
        .forEach((item) => {
            events.push({
                type: "treatment",
                date: item.date || "",
                time: "",
                title: item.description || t("treatment"),
                description: `${item.toothNumber ? `#${item.toothNumber} · ` : ""}${money(item.fee)}`,
                icon: "🦷",
                status: item.status || "planned",
            });
        });

    // Treatment plans
    state.treatmentPlans
        .filter((item) => item.patientId === patientId)
        .forEach((item) => {
            events.push({
                type: "treatment-plan",
                date: item.updatedAt || item.createdAt || "",
                time: "",
                title: item.procedure || t("treatmentPlan"),
                description: `${item.toothNumber ? `#${item.toothNumber} · ` : ""}${t(
                    "diagnosis",
                )}: ${item.diagnosis || "—"}`,
                icon: "📋",
                status: item.status || "planned",
            });
        });

    // Prescriptions
    state.prescriptions
        .filter((item) => item.patientId === patientId)
        .forEach((item) => {
            events.push({
                type: "prescription",
                date: item.date || "",
                time: "",
                title: t("prescriptions"),
                description:
                    item.medications?.map((medication) => medication.name).join(", ") ||
                    t("medication"),
                icon: "💊",
                status: "",
            });
        });

    // X-rays
    state.xrays
        .filter((item) => item.patientId === patientId)
        .forEach((item) => {
            events.push({
                type: "xray",
                id: item.id,
                date: item.date || "",
                time: item.time || "",
                title: item.filename || t("xrays"),
                description: `${t(item.type || "other")}${item.toothTag ? ` · ${t("toothNumber")} #${item.toothTag}` : ""}`,
                icon: "📷",
                status: "",
                imageUrl: item.base64Data,
            });
        });

    // Newest first
    events.sort((a, b) => {
        const first = `${b.date} ${b.time}`.trim();
        const second = `${a.date} ${a.time}`.trim();
        return first.localeCompare(second);
    });

    if (!events.length) {
        return `
            <div class="timeline-empty">
                ${t("noVisits")}
            </div>
        `;
    }

    return `
    <div class="patient-timeline">
        ${events.map((event) => `
            <div class="timeline-event ${event.type === "xray" ? "timeline-event-clickable" : ""}" ${event.type === "xray" ? `data-open-xray="${event.id}" title="${t("xrays")}"` : ""}>
                <div class="timeline-marker">${event.icon}</div>
                <div class="timeline-content">
                    <div class="timeline-event-header">
                        <div>
                            <strong>${esc(event.title)}</strong>
                            <small>${esc(event.date)}${event.time ? ` · ${esc(event.time)}` : ""}</small>
                        </div>
                        ${event.status ? `<span class="badge">${t(event.status)}</span>` : ""}
                    </div>
                    <p>${esc(event.description)}</p>
                    ${event.type === "xray" && event.imageUrl ? `
                        <div class="timeline-xray-preview" style="margin-top: 8px; display: inline-flex; align-items: center; gap: 8px;">
                            <img src="${esc(event.imageUrl)}" 
                                 alt="${esc(event.title)}" 
                                 style="width: 56px; height: 56px; object-fit: cover; border-radius: var(--radius-sm, 6px); border: 1px solid var(--border); box-shadow: 0 1px 3px rgba(0,0,0,0.06);" 
                                 onerror="this.style.display='none'" 
                                 loading="lazy">
                            <span class="badge" style="cursor: pointer; display: inline-flex; align-items: center; gap: 4px;">
                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>
                                ${t("view")}
                            </span>
                        </div>
                    ` : ""}
                </div>
            </div>
        `).join("")}
    </div>`;
}
