let onlineTreatmentPlanRequest = 0;

function mapApiTreatmentPlan(plan) {
    return {
        ...plan,
        clinicId: plan.clinic_id,
        patientId: plan.patient_id,
        doctorId: plan.doctor_id,
        toothNumber: plan.tooth_number,
        createdBy: plan.created_by,
        createdAt: plan.created_at,
        updatedAt: plan.updated_at,
    };
}

function selectedTreatmentPlanPatient() {
    const patient = state.selectedPatient;
    return Number.isInteger(patient?.id) && patient.id > 0 ? patient : null;
}

function canModifyTreatmentPlans() {
    return !window.AERODENT_ONLINE || (
        !state.treatmentPlanReadOnly
        && hasPermission("treatment_plans.create")
        && hasPermission("treatment_plans.update")
        && hasPermission("treatment_plans.delete")
    );
}

function treatmentPlanErrorMessage(error) {
    if (error?.status === 0) return t("treatmentNetworkError") || "Network error";
    if (error?.status === 403) return t("readOnly");
    if (error?.status === 404) return t("treatmentUnavailable") || "Not found";
    if (error?.status === 400 || error?.status === 422) return error.message || t("treatmentInvalid");
    return error?.message || t("unableSaveTreatmentPlan");
}

function treatmentPlanPagination() {
    if (!window.AERODENT_ONLINE || state.treatmentPlanPages <= 1) return "";
    return `<div class="patient-pagination">
        <button class="button button-ghost" data-treatment-plan-page="previous" ${state.treatmentPlanPage <= 1 ? "disabled" : ""}>${t("previous")}</button>
        <span>${state.treatmentPlanPage} / ${state.treatmentPlanPages}</span>
        <button class="button button-ghost" data-treatment-plan-page="next" ${state.treatmentPlanPage >= state.treatmentPlanPages ? "disabled" : ""}>${t("next")}</button>
    </div>`;
}

async function loadOnlineTreatmentPlans() {
    if (!window.AERODENT_ONLINE) return;
    const requestId = ++onlineTreatmentPlanRequest;
    const patient = selectedTreatmentPlanPatient();
    if (!patient) {
        state.treatmentPlanLoading = false;
        state.treatmentPlanReadOnly = false;
        state.treatmentPlans = [];
        state.treatmentPlanError = "";
        render();
        return;
    }

    const patientId = patient.id;
    state.treatmentPlanLoading = true;
    state.treatmentPlanReadOnly = !hasPermission("treatment_plans.update");
    state.treatmentPlanError = "";
    render();

    try {
        const params = new URLSearchParams({
            patient_id: String(patientId),
            page: String(state.treatmentPlanPage),
            per_page: String(state.treatmentPlanPerPage),
        });
        const response = await window.AERODENT_API.get(`/api/treatment-plans?${params}`);
        if (requestId !== onlineTreatmentPlanRequest || selectedTreatmentPlanPatient()?.id !== patientId) return;
        state.treatmentPlans = (response.data || []).map(mapApiTreatmentPlan);
        state.treatmentPlanTotal = response.meta?.total || 0;
        state.treatmentPlanPages = response.meta?.pages || 0;
    } catch (error) {
        if (requestId !== onlineTreatmentPlanRequest || selectedTreatmentPlanPatient()?.id !== patientId) return;
        state.treatmentPlanReadOnly = error.status === 403;
        state.treatmentPlanError = treatmentPlanErrorMessage(error);
        if (error.status === 404) state.treatmentPlans = [];
    } finally {
        if (requestId === onlineTreatmentPlanRequest && selectedTreatmentPlanPatient()?.id === patientId) {
            state.treatmentPlanLoading = false;
            render();
        }
    }
}

function addTreatmentPlan() {
    const patient = selectedTreatmentPlanPatient();
    if (!patient) {
        toast(t("selectPatientFirst"));
        return;
    }
    if (window.AERODENT_ONLINE && !canModifyTreatmentPlans()) return;

    const patientField = window.AERODENT_ONLINE
        ? `<div class="field full-span"><label>${t("patient")}</label><input value="${esc(patient.name)}" disabled></div>`
        : `<div class="field full-span"><label>${t("patient")}</label><select name="patientId" required><option value="">${t("selectPatient")}</option>${state.patients.map((p) => `<option value="${p.id}" ${p.id === patient.id ? "selected" : ""}>${esc(p.name)} · ${esc(p.phone || "")}</option>`).join("")}</select></div>`;

    modal(
        t("addTreatmentPlan"),
        `<form id="treatmentPlanForm" class="form-grid">
            ${patientField}
            <div class="field">
                <label>${t("tooth")}</label>
                <input type="number" name="toothNumber" min="1" max="85" placeholder="1–85">
            </div>
            <div class="field">
                <label>${t("diagnosis")}</label>
                <input name="diagnosis" required>
            </div>
            <div class="field full-span">
                <label>${t("procedure")}</label>
                <input name="procedure" required>
            </div>
            <div class="field">
                <label>${t("fee")}</label>
                <input type="number" name="fee" min="0" step="0.01" value="0">
            </div>
            <div class="field">
                <label>${t("priority")}</label>
                <select name="priority">
                    <option value="low">${t("low")}</option>
                    <option value="medium" selected>${t("medium")}</option>
                    <option value="high">${t("high")}</option>
                </select>
            </div>
            <div class="field">
                <label>${t("status")}</label>
                <select name="status">
                    <option value="planned" selected>${t("planned")}</option>
                    <option value="accepted">${t("accepted")}</option>
                    <option value="scheduled">${t("scheduled")}</option>
                    <option value="in-progress">${t("inProgress")}</option>
                    <option value="completed">${t("completed")}</option>
                    <option value="cancelled">${t("cancelled")}</option>
                </select>
            </div>
            <div class="field full-span">
                <label>${t("notes")}</label>
                <textarea name="notes" rows="3"></textarea>
            </div>
            <div class="form-actions full-span">
                <button class="button button-primary" type="submit">${t("save")}</button>
            </div>
        </form>`,
    );

    $("#treatmentPlanForm").onsubmit = async (event) => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(event.target));

        if (window.AERODENT_ONLINE) {
            if (selectedTreatmentPlanPatient()?.id !== patient.id || state.treatmentPlanSaving) return;
            state.treatmentPlanSaving = true;
            try {
                const payload = {
                    patient_id: patient.id,
                    tooth_number: data.toothNumber ? Number(data.toothNumber) : null,
                    diagnosis: data.diagnosis,
                    procedure: data.procedure,
                    fee: data.fee || "0",
                    priority: data.priority || "medium",
                    status: data.status || "planned",
                    notes: data.notes || "",
                };
                await window.AERODENT_API.post("/api/treatment-plans", payload);
                $("#modal").classList.remove("show");
                state.treatmentPlanPage = 1;
                await loadOnlineTreatmentPlans();
                toast(t("savedOnline"));
            } catch (error) {
                toast(treatmentPlanErrorMessage(error));
            } finally {
                state.treatmentPlanSaving = false;
            }
            return;
        }

        const offlinePatient = state.patients.find((item) => item.id === Number(data.patientId));
        if (!offlinePatient) return;

        try {
            await dbPut("treatmentPlans", {
                patientId: offlinePatient.id,
                toothNumber: Number(data.toothNumber) || null,
                diagnosis: data.diagnosis,
                procedure: data.procedure,
                fee: Number(data.fee) || 0,
                priority: data.priority,
                status: data.status,
                notes: data.notes || "",
                createdAt: new Date().toISOString(),
                updatedAt: new Date().toISOString(),
            });
            state.selectedPatient = offlinePatient;
            $("#modal").classList.remove("show");
            await refresh();
        } catch (error) {
            console.error("Failed to create treatment plan:", error);
            toast(t("unableSaveTreatmentPlan"));
        }
    };
}

function editTreatmentPlan(id) {
    const plan = state.treatmentPlans.find((item) => item.id === id);
    const patient = selectedTreatmentPlanPatient();
    if (!plan || !patient || plan.patientId !== patient.id) return;
    if (window.AERODENT_ONLINE && !canModifyTreatmentPlans()) return;

    modal(
        t("edit"),
        `<form id="editTreatmentPlanForm" class="form-grid">
            <div class="field">
                <label>${t("tooth")}</label>
                <input type="number" name="toothNumber" min="1" max="85" value="${esc(plan.toothNumber || "")}">
            </div>
            <div class="field">
                <label>${t("diagnosis")}</label>
                <input name="diagnosis" required value="${esc(plan.diagnosis || "")}">
            </div>
            <div class="field full-span">
                <label>${t("procedure")}</label>
                <input name="procedure" required value="${esc(plan.procedure || "")}">
            </div>
            <div class="field">
                <label>${t("fee")}</label>
                <input type="number" name="fee" min="0" step="0.01" value="${Number(plan.fee || 0)}">
            </div>
            <div class="field">
                <label>${t("priority")}</label>
                <select name="priority">
                    <option value="low" ${plan.priority === "low" ? "selected" : ""}>${t("low")}</option>
                    <option value="medium" ${plan.priority === "medium" || !plan.priority ? "selected" : ""}>${t("medium")}</option>
                    <option value="high" ${plan.priority === "high" ? "selected" : ""}>${t("high")}</option>
                </select>
            </div>
            <div class="field">
                <label>${t("status")}</label>
                <select name="status">
                    <option value="planned" ${plan.status === "planned" || !plan.status ? "selected" : ""}>${t("planned")}</option>
                    <option value="accepted" ${plan.status === "accepted" ? "selected" : ""}>${t("accepted")}</option>
                    <option value="scheduled" ${plan.status === "scheduled" ? "selected" : ""}>${t("scheduled")}</option>
                    <option value="in-progress" ${plan.status === "in-progress" ? "selected" : ""}>${t("inProgress")}</option>
                    <option value="completed" ${plan.status === "completed" ? "selected" : ""}>${t("completed")}</option>
                    <option value="cancelled" ${plan.status === "cancelled" ? "selected" : ""}>${t("cancelled")}</option>
                </select>
            </div>
            <div class="field full-span">
                <label>${t("notes")}</label>
                <textarea name="notes" rows="3">${esc(plan.notes || "")}</textarea>
            </div>
            <div class="form-actions full-span">
                <button class="button button-primary" type="submit">${t("save")}</button>
            </div>
        </form>`,
    );

    $("#editTreatmentPlanForm").onsubmit = async (event) => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(event.target));

        if (window.AERODENT_ONLINE) {
            if (selectedTreatmentPlanPatient()?.id !== patient.id || state.treatmentPlanSaving) return;
            state.treatmentPlanSaving = true;
            try {
                const payload = {
                    tooth_number: data.toothNumber ? Number(data.toothNumber) : null,
                    diagnosis: data.diagnosis,
                    procedure: data.procedure,
                    fee: data.fee || "0",
                    priority: data.priority,
                    status: data.status,
                    notes: data.notes || "",
                };
                const response = await window.AERODENT_API.patch(`/api/treatment-plans/${plan.id}`, payload);
                const index = state.treatmentPlans.findIndex((item) => item.id === plan.id);
                if (index !== -1 && selectedTreatmentPlanPatient()?.id === patient.id) {
                    state.treatmentPlans[index] = mapApiTreatmentPlan(response.data);
                }
                $("#modal").classList.remove("show");
                render();
                toast(t("savedOnline"));
            } catch (error) {
                toast(treatmentPlanErrorMessage(error));
            } finally {
                state.treatmentPlanSaving = false;
            }
            return;
        }

        try {
            await dbPut("treatmentPlans", {
                ...plan,
                toothNumber: Number(data.toothNumber) || null,
                diagnosis: data.diagnosis,
                procedure: data.procedure,
                fee: Number(data.fee) || 0,
                priority: data.priority,
                status: data.status,
                notes: data.notes || "",
                updatedAt: new Date().toISOString(),
            });
            $("#modal").classList.remove("show");
            await refresh();
        } catch (error) {
            console.error("Failed to update treatment plan:", error);
            toast(t("unableSaveTreatmentPlan"));
        }
    };
}

async function deleteTreatmentPlan(id) {
    const plan = state.treatmentPlans.find((item) => item.id === id);
    const patient = selectedTreatmentPlanPatient();
    if (!plan || !patient || plan.patientId !== patient.id) return;
    if (window.AERODENT_ONLINE && !canModifyTreatmentPlans()) return;
    if (!confirm(t("confirmDeleteTreatment") || "Delete this treatment plan?")) return;

    if (window.AERODENT_ONLINE) {
        if (state.treatmentPlanSaving) return;
        state.treatmentPlanSaving = true;
        try {
            await window.AERODENT_API.delete(`/api/treatment-plans/${id}`);
            if (selectedTreatmentPlanPatient()?.id === patient.id) {
                state.treatmentPlans = state.treatmentPlans.filter((item) => item.id !== id);
                state.treatmentPlanTotal = Math.max(0, state.treatmentPlanTotal - 1);
                if (!state.treatmentPlans.length && state.treatmentPlanPage > 1) {
                    state.treatmentPlanPage -= 1;
                }
                await loadOnlineTreatmentPlans();
            }
            toast(t("treatmentPlanDeleted") || "Treatment plan deleted");
        } catch (error) {
            toast(treatmentPlanErrorMessage(error));
        } finally {
            state.treatmentPlanSaving = false;
        }
        return;
    }

    await dbDelete("treatmentPlans", id);
    await refresh();
    showUndo(t("treatmentPlanDeleted") || "Treatment plan deleted", async () => {
        await dbPut("treatmentPlans", plan);
        await refresh();
    });
}

function renderTreatmentPlanList(patientId) {
    if (state.treatmentPlanLoading) {
        return `<p class="muted">${t("loading")}</p>`;
    }
    if (state.treatmentPlanError) {
        return `<p class="login-error">${esc(state.treatmentPlanError)}</p>`;
    }

    const plans = window.AERODENT_ONLINE
        ? state.treatmentPlans
        : state.treatmentPlans.filter((item) => item.patientId === patientId);

    if (!plans.length) {
        return `<p class="muted">${t("noTreatmentPlans")}</p>`;
    }

    const editable = canModifyTreatmentPlans();

    return `
        <div class="treatment-plan-list">
            ${plans.map((item) => `
                <div class="treatment-plan-item">
                    <div class="treatment-plan-main">
                        <div class="treatment-plan-tooth">${item.toothNumber ? `#${esc(item.toothNumber)}` : "—"}</div>
                        <div>
                            <strong>${esc(item.procedure)}</strong>
                            <small>${t("diagnosis")}: ${esc(item.diagnosis || "—")}</small>
                        </div>
                    </div>
                    <div class="treatment-plan-details">
                        <span class="badge">${t(item.priority || "medium")}</span>
                        <span class="badge">${t(item.status || "planned")}</span>
                        <strong>${money(item.fee)}</strong>
                        ${editable ? `
                            <div class="treatment-plan-actions">
                                <button type="button" class="button button-ghost" data-edit-treatment-plan="${item.id}">${t("edit")}</button>
                                <button type="button" class="button treatment-plan-delete" data-delete-treatment-plan="${item.id}">×</button>
                            </div>
                        ` : ""}
                    </div>
                </div>
            `).join("")}
        </div>
        ${treatmentPlanPagination()}
    `;
}

function renderTreatmentPlans() {
    const patient = selectedTreatmentPlanPatient();
    const patientOptions = state.patients.map((item) =>
        `<option value="${item.id}" ${item.id === patient?.id ? "selected" : ""}>${esc(item.name)} · ${esc(item.phone || "")}</option>`
    ).join("");

    const editable = patient && canModifyTreatmentPlans();
    const readOnly = window.AERODENT_ONLINE && patient && !editable ? `<p class="muted">${t("readOnly")}</p>` : "";

    return `
        <section class="card">
            <div class="card-heading">
                <div>
                    <h2>${t("treatmentPlan")}</h2>
                    ${patient ? `<p class="muted">${esc(patient.name)}</p>` : `<p class="muted">${t("selectPatient")}</p>`}
                </div>
                ${editable ? `
                    <button class="button button-primary" data-action="addTreatmentPlan">
                        ＋ ${t("addTreatmentPlan")}
                    </button>
                ` : ""}
            </div>
            <div class="field treatment-plan-patient-picker">
                <label>${t("patient")}</label>
                <select id="treatmentPlanPatientSelect">
                    <option value="">${t("selectPatient")}</option>
                    ${patientOptions}
                </select>
            </div>
            ${readOnly}
            ${patient ? renderTreatmentPlanList(patient.id) : `<div class="timeline-empty">${t("selectPatient")}</div>`}
        </section>
    `;
}
