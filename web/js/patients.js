function mapApiPatient(patient) {
    return {
        ...patient,
        clinicId: patient.clinic_id,
        workStudy: patient.work_study,
        medicalFlags: patient.medical_flags,
        createdBy: patient.created_by,
        createdAt: patient.created_at,
        updatedAt: patient.updated_at,
    };
}

function patientApiPayload(data) {
    const payload = {
        name: data.name,
        phone: data.phone || null,
        location: data.location || null,
        work_study: data.workStudy ?? data.work_study ?? null,
        dob: data.dob || null,
        gender: data.gender || null,
    };
    for (const [frontendField, backendField] of [
        ["allergies", "allergies"],
        ["medicalFlags", "medical_flags"],
        ["notes", "notes"],
    ]) {
        if (Object.prototype.hasOwnProperty.call(data, frontendField)) {
            payload[backendField] = data[frontendField] ?? null;
        }
    }
    return payload;
}

async function refreshOnlinePatients(preserveEmptySelection = false) {
    state.patientLoading = true;
    state.patientError = "";
    render();
    try {
        const params = new URLSearchParams({
            page: String(state.patientPage),
            per_page: String(state.patientPerPage),
        });
        if (state.patientSearch.trim()) params.set("q", state.patientSearch.trim());
        const response = await window.AERODENT_API.get(`/api/patients?${params}`);
        state.patients = (response.data || []).map(mapApiPatient);
        state.patientTotal = response.meta?.total || 0;
        state.patientPages = response.meta?.pages || 0;
        state.selectedPatient = preserveEmptySelection
            ? null
            : state.selectedPatient
                ? state.patients.find((patient) => patient.id === state.selectedPatient.id) || null
                : state.patients[0] || null;
        if (state.selectedPatient) {
            state.treatmentPatientId ??= state.selectedPatient.id;
            state.treatmentPlanPatientId ??= state.selectedPatient.id;
            state.prescriptionPatientId ??= state.selectedPatient.id;
        }
    } catch (error) {
        state.patientError = error.message;
    } finally {
        state.patientLoading = false;
        render();
    }
}

function onlinePatientClinicalFieldsAllowed() {
    return state.auth.user?.role !== "secretary";
}

function patientPagination() {
    if (!window.AERODENT_ONLINE || state.patientPages <= 1) return "";
    return `<div class="patient-pagination"><button class="button button-ghost" data-patient-page="previous" ${state.patientPage <= 1 ? "disabled" : ""}>${t("previous")}</button><span>${state.patientPage} / ${state.patientPages}</span><button class="button button-ghost" data-patient-page="next" ${state.patientPage >= state.patientPages ? "disabled" : ""}>${t("next")}</button></div>`;
}

function patientRow(patient) {
    const rawName = (patient.name || "").trim();
    const parts = rawName.split(/\s+/);
    const initials = parts.length > 1
        ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
        : (parts[0] ? parts[0].slice(0, 2).toUpperCase() : "PT");
    const hasAlert = !!(patient.allergies || patient.medicalFlags || patient.medical_flags);
    const alertText = patient.allergies || patient.medicalFlags || patient.medical_flags || "";

    return `
      <div class="patient-row" data-patient-id="${patient.id}">
        <div class="patient-row-avatar">${initials}</div>
        <div class="patient-row-info">
          <b>${esc(patient.name)}</b>
          <small><bdi dir="ltr">${esc(patient.phone || t("noPhone"))}</bdi></small>
        </div>
        <div class="patient-row-status">
          ${hasAlert
            ? `<span class="badge badge-danger" title="${esc(alertText)}">⚠ ${t("allergies")}</span>`
            : `<span class="badge badge-success">✓ ${t("healthy")}</span>`}
        </div>
      </div>
    `;
}
function patientSelector(id, selectedPatient) {
    const options = state.patients
        .map(
            (patient) =>
                `<option value="${patient.id}" ${patient.id === selectedPatient?.id ? "selected" : ""}>${esc(patient.name)} · ${esc(patient.phone || "")}</option>`,
        )
        .join("");
    return `<div class="field patient-context-picker"><label>${t("patient")}</label><select id="${id}"><option value="">${t("selectPatient")}</option>${options}</select></div>`;
}
function renderPatients() {
    const content = state.patientLoading
        ? `<p class="muted">${t("loading")}</p>`
        : state.patientError
            ? `<p class="login-error">${esc(state.patientError)}</p>`
            : state.patients.length
                ? state.patients.map(patientRow).join("")
                : `<p class="muted">${t("noPatients")}</p>`;
    const canDelete = !window.AERODENT_ONLINE || hasPermission("patients.delete");
    return `<section class="content-grid"><div class="card"><div class="card-heading"><h2>${t("patients")}</h2><button class="button button-primary" data-action="newPatient">＋ ${t("newPatient")}</button></div>${patientSelector("patientRecordSelect", state.selectedPatient)}<div id="patientList">${content}</div>${window.AERODENT_ONLINE ? `<small class="muted">${state.patientTotal} ${t("patients")}</small>` : ""}${patientPagination()}</div><div class="card">${state.selectedPatient ? patientForm(state.selectedPatient, canDelete) : `<p class="muted">${t("selectPatient")}</p>`}</div></section>`;
}
function patientForm(patient, canDelete = true) {
    const clinicalFields = !window.AERODENT_ONLINE || onlinePatientClinicalFieldsAllowed();
    return `<div class="card-heading"><h2>${esc(patient.name)}</h2><span class="badge ${patient.allergies ? "badge-danger" : ""}">${patient.allergies ? "! " + esc(patient.allergies) : t("healthy")}</span></div>${patient.medicalFlags ? `<div class="alert-banner">⚠ ${esc(patient.medicalFlags)}</div>` : ""}<form id="patientForm" class="form-grid"><div class="field"><label>${t("patient")}</label><input name="name" value="${esc(patient.name)}" required></div><div class="field"><label>${t("phone")}</label><input name="phone" value="${esc(patient.phone)}"></div><div class="field"><label>${t("location")}</label><input name="location" value="${esc(patient.location)}"></div><div class="field"><label>${t("workStudy")}</label><input name="workStudy" value="${esc(patient.workStudy)}"></div><div class="field"><label>${t("dob")}</label><input type="date" name="dob" value="${esc(patient.dob)}"></div><div class="field"><label>${t("gender")}</label><select name="gender"><option
    value="Female"
    ${patient.gender === "Female" || !patient.gender ? "selected" : ""}
>
    ${t("female")}
</option>

<option
    value="Male"
    ${patient.gender === "Male" ? "selected" : ""}
>
    ${t("male")}
</option></select></div>${clinicalFields ? `<div class="field"><label>${t("allergies")}</label><input name="allergies" value="${esc(patient.allergies)}"></div><div class="field full-span"><label>${t("medicalFlags")}</label><input name="medicalFlags" value="${esc(patient.medicalFlags)}"></div><div class="field full-span"><label>${t("notes")}</label><textarea name="notes" rows="3">${esc(patient.notes)}</textarea></div>` : ""}<div class="form-actions full-span"><button type="submit" class="button button-primary">${t("save")}</button>${canDelete ? `<button type="button" class="button delete-patient-button" data-delete-patient="${patient.id}">${t("deletePatient")}</button>` : ""}</div></form><div
    class="card-heading"
    style="margin-top:28px"
>
    <div>
        <h3>
            ${t("clinicalHistory")}
        </h3>

        <p class="muted">
            ${t("patientTimeline")}
        </p>
    </div>
</div>

${renderPatientTimeline(patient.id)}`;
}

async function getPatientBackup(patientId) {
    const relatedStores = [
        "odontograms",
        "appointments",
        "treatments",
        "treatmentPlans",
        "invoices",
        "prescriptions",
        "xrays",
    ];
    const backup = {
        patient: await dbGet("patients", patientId),

        related: {},
    };

    for (const store of relatedStores) {
        const records = await dbGetAll(store);

        backup.related[store] = records.filter(
            (record) => record.patientId === patientId,
        );
    }

    return backup;
}

async function restorePatientBackup(backup) {
    if (!backup?.patient) {
        throw new Error("Invalid patient backup");
    }

    await dbPut("patients", backup.patient);

    for (const [store, records] of Object.entries(backup.related)) {
        for (const record of records) {
            await dbPut(store, record);
        }
    }

    await refresh();
}
