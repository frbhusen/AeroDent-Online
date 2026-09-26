let onlinePrescriptionRequest = 0;

function mapApiPrescription(item) {
    return {
        ...item,
        clinicId: item.clinic_id,
        patientId: item.patient_id,
        doctorId: item.doctor_id,
        medications: Array.isArray(item.medications) ? item.medications : [],
        createdBy: item.created_by,
        createdAt: item.created_at,
        updatedAt: item.updated_at,
    };
}

function selectedPrescriptionPatient() {
    const patient = state.selectedPatient;
    return Number.isInteger(patient?.id) && patient.id > 0 ? patient : null;
}

function canModifyPrescriptions() {
    return !window.AERODENT_ONLINE || (
        !state.prescriptionReadOnly
        && hasPermission("prescriptions.create")
        && hasPermission("prescriptions.update")
        && hasPermission("prescriptions.delete")
    );
}

function prescriptionErrorMessage(error) {
    if (error?.status === 0) return t("treatmentNetworkError") || "Network error";
    if (error?.status === 403) return t("readOnly");
    if (error?.status === 404) return t("treatmentUnavailable") || "Not found";
    return error?.message || "Failed to process prescription";
}

async function loadOnlinePrescriptions() {
    if (!window.AERODENT_ONLINE) return;
    const requestId = ++onlinePrescriptionRequest;
    const patient = selectedPrescriptionPatient();
    if (!patient) {
        state.prescriptionLoading = false;
        state.prescriptionReadOnly = false;
        state.prescriptions = [];
        state.prescriptionError = "";
        render();
        return;
    }

    const patientId = patient.id;
    state.prescriptionLoading = true;
    state.prescriptionReadOnly = !hasPermission("prescriptions.update");
    state.prescriptionError = "";
    render();

    try {
        const response = await window.AERODENT_API.get(`/api/prescriptions?patient_id=${patientId}&per_page=100`);
        if (requestId !== onlinePrescriptionRequest || selectedPrescriptionPatient()?.id !== patientId) return;
        state.prescriptions = (response.data || []).map(mapApiPrescription);
    } catch (error) {
        if (requestId !== onlinePrescriptionRequest || selectedPrescriptionPatient()?.id !== patientId) return;
        state.prescriptionReadOnly = error.status === 403;
        state.prescriptionError = prescriptionErrorMessage(error);
        if (error.status === 404) state.prescriptions = [];
    } finally {
        if (requestId === onlinePrescriptionRequest && selectedPrescriptionPatient()?.id === patientId) {
            state.prescriptionLoading = false;
            render();
        }
    }
}

function renderPrescriptions() {
    const prescriptionPatient = selectedPrescriptionPatient();
    const prescriptions = window.AERODENT_ONLINE
        ? state.prescriptions
        : state.prescriptions.filter((item) => item.patientId === prescriptionPatient?.id);

    const safePrescriptions = prescriptions.filter((item) => Array.isArray(item.medications));
    const patientOptions = state.patients
        .map((patient) =>
            `<option value="${patient.id}" ${patient.id === prescriptionPatient?.id ? "selected" : ""}>
                ${esc(patient.name)} · ${esc(patient.phone || "")}
            </option>`
        )
        .join("");

    const editable = prescriptionPatient && canModifyPrescriptions();
    const readOnly = window.AERODENT_ONLINE && prescriptionPatient && !editable ? `<p class="muted">${t("readOnly")}</p>` : "";

    let contentHtml = "";
    if (state.prescriptionLoading) {
        contentHtml = `<p class="muted">${t("loading")}</p>`;
    } else if (state.prescriptionError) {
        contentHtml = `<p class="login-error">${esc(state.prescriptionError)}</p>`;
    } else if (!prescriptionPatient) {
        contentHtml = `<p class="muted">${t("selectPatient")}</p>`;
    } else if (!safePrescriptions.length) {
        contentHtml = `<p class="muted">${t("noVisits")}</p>`;
    } else {
        contentHtml = safePrescriptions.map((item) => `
            <div class="prescription-row">
                <div>
                    <b>${item.medications.map((m) => esc(m.name)).join(", ")}</b>
                    <small>${esc(item.date)} · ${item.medications.length} ${t("medication")}</small>
                </div>
                <div class="prescription-actions">
                    ${editable ? `<button class="button button-ghost" data-edit-prescription="${item.id}">${t("edit")}</button>` : ""}
                    ${editable ? `<button class="button button-ghost" data-delete-prescription="${item.id}">×</button>` : ""}
                    <button class="button button-ghost" data-print-prescription="${item.id}">${t("print")}</button>
                </div>
            </div>
            <div class="prescription-print ${state.printPrescriptionId === item.id ? "active" : ""}">
                <header>
                    <h1>${esc(state.settings.clinicName || state.settings.name || t("appName"))}</h1>
                    <p>${esc(state.settings.doctorName || "")}</p>
                </header>
                <h2>${t("prescriptions")}</h2>
                <p><b>${t("patient")}:</b> ${esc(prescriptionPatient?.name || "")}</p>
                <p><b>${t("date")}:</b> ${esc(item.date)}</p>
                <hr>
                ${item.medications.map((m) => `
                    <div class="prescription-medication">
                        <h3>${esc(m.name)}</h3>
                        <p>${t("dosage")}: ${esc(m.dosage || "—")} · ${t("frequency")}: ${esc(m.frequency || "—")} · ${t("duration")}: ${esc(m.duration || "—")}</p>
                        <p>${t("instructions")}: ${esc(m.instructions || "—")}</p>
                    </div>
                `).join("")}
                <hr>
                <p>${esc(item.notes || "")}</p>
                <footer>${esc(state.settings.doctorName || "")}</footer>
            </div>
        `).join("");
    }

    return `
        <section class="content-grid prescriptions-screen">
            <div class="card">
                <div class="card-heading">
                    <h2>${t("prescriptions")}</h2>
                    ${editable ? `
                        <button class="button button-primary" data-action="addPrescription">
                            ＋ ${t("addPrescription")}
                        </button>
                    ` : ""}
                </div>
                <div class="field treatment-patient-picker">
                    <label>${t("patient")}</label>
                    <select id="prescriptionPatientSelect">
                        <option value="">${t("selectPatient")}</option>
                        ${patientOptions}
                    </select>
                </div>
                ${readOnly}
                ${contentHtml}
            </div>
            <div class="card">
                <div class="card-heading">
                    <h2>${t("commonMedications")}</h2>
                </div>
                <p class="muted">${t("quickMedicationsHint")}</p>
                <div class="quick-med-list">
                    ${COMMON_DENTAL_MEDICATIONS.map((med) => `
                        <button type="button" class="quick-med-chip" data-quick-med="${esc(med.name)}" data-dosage="${esc(med.dosage)}" data-frequency="${esc(med.frequency)}" data-duration="${esc(med.duration)}" data-instructions="${esc(med.instructions)}">
                            <span>💊</span>
                            <span>${esc(med.name)}</span>
                            <small class="muted">(${esc(med.dosage)})</small>
                        </button>
                    `).join("")}
                </div>
            </div>
        </section>
    `;
}

const COMMON_DENTAL_MEDICATIONS = [
    { name: "Amoxicillin", dosage: "500mg", frequency: "3 times daily", duration: "7 days", instructions: "Take with or after food" },
    { name: "Augmentin (Amoxicillin/Clavulanate)", dosage: "625mg", frequency: "2 times daily", duration: "7 days", instructions: "Take at start of meal" },
    { name: "Ibuprofen", dosage: "400mg", frequency: "3 times daily", duration: "3-5 days", instructions: "Take after meals for pain/swelling" },
    { name: "Paracetamol", dosage: "500mg", frequency: "Every 6 hours as needed", duration: "3-5 days", instructions: "Do not exceed 4g/day" },
    { name: "Metronidazole", dosage: "500mg", frequency: "3 times daily", duration: "5-7 days", instructions: "Avoid alcohol completely" },
    { name: "Azithromycin", dosage: "500mg", frequency: "Once daily", duration: "3 days", instructions: "Take 1 hour before or 2 hours after meals" },
    { name: "Chlorhexidine Gluconate 0.12%", dosage: "15ml", frequency: "Twice daily", duration: "14 days", instructions: "Rinse mouth for 30s after brushing" },
];

function prescriptionMedicationFields(medication = {}, index = 0) {
    return `
        <div class="prescription-edit-medication" data-medication-index="${index}">
            <div class="medication-card-header">
                <div class="medication-card-title">
                    <span class="med-pill-badge">💊 ${t("medicationNumber")} #${index + 1}</span>
                </div>
                <button type="button" class="medication-delete-button" data-delete-medication="${index}" title="${t("deleteMedication")}" aria-label="${t("deleteMedication")}">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
                    <span>${t("remove")}</span>
                </button>
            </div>
            <div class="medication-card-body">
                <div class="field full-span">
                    <label class="med-label">
                        <span>${t("medication")}</span>
                        <span class="required-star">*</span>
                    </label>
                    <input name="name${index}" value="${esc(medication.name || "")}" placeholder="${t("medicationPlaceholder")}" required list="commonDentalMedsList">
                </div>
                <div class="medication-grid-row">
                    <div class="field">
                        <label class="med-label">${t("dosage")}</label>
                        <input name="dosage${index}" value="${esc(medication.dosage || "")}" placeholder="${t("dosagePlaceholder")}">
                    </div>
                    <div class="field">
                        <label class="med-label">${t("frequency")}</label>
                        <input name="frequency${index}" value="${esc(medication.frequency || "")}" placeholder="${t("frequencyPlaceholder")}">
                    </div>
                    <div class="field">
                        <label class="med-label">${t("duration")}</label>
                        <input name="duration${index}" value="${esc(medication.duration || "")}" placeholder="${t("durationPlaceholder")}">
                    </div>
                    <div class="field">
                        <label class="med-label">${t("instructions")}</label>
                        <input name="instructions${index}" value="${esc(medication.instructions || "")}" placeholder="${t("instructionsPlaceholder")}">
                    </div>
                </div>
            </div>
        </div>
    `;
}

function prescriptionForm(record) {
    const medications = record?.medications?.length ? record.medications : [{}];
    return `
        <datalist id="commonDentalMedsList">
            ${COMMON_DENTAL_MEDICATIONS.map((m) => `<option value="${esc(m.name)}">${esc(m.dosage)} · ${esc(m.frequency)}</option>`).join("")}
        </datalist>
        <div id="prescriptionMedications" class="prescription-medications-list full-span">
            ${medications.map((medication, index) => prescriptionMedicationFields(medication, index)).join("")}
        </div>
        <div class="add-medication-bar full-span">
            <button type="button" class="button button-dashed add-medication-btn" id="addMedicationBtn">
                <span class="add-icon">＋</span>
                <span>${t("addMedication")}</span>
            </button>
        </div>
        <div class="field full-span">
            <label class="med-label">${t("notes")}</label>
            <textarea name="notes" rows="2" placeholder="${t("notes")}...">${esc(record?.notes || "")}</textarea>
        </div>
        <div class="form-actions full-span">
            <button class="button button-primary" type="submit">${t("save")}</button>
        </div>
    `;
}

function renumberMedications() {
    const container = $("#prescriptionMedications");
    if (!container) return;
    const cards = container.querySelectorAll(".prescription-edit-medication");
    if (cards.length === 0) {
        container.insertAdjacentHTML("beforeend", prescriptionMedicationFields({}, 0));
        bindPrescriptionMedicationControls();
        return;
    }
    cards.forEach((card, idx) => {
        card.setAttribute("data-medication-index", idx);
        const titleBadge = card.querySelector(".med-pill-badge");
        if (titleBadge) {
            titleBadge.textContent = `💊 ${t("medicationNumber")} #${idx + 1}`;
        }
        const delBtn = card.querySelector("[data-delete-medication]");
        if (delBtn) {
            delBtn.setAttribute("data-delete-medication", idx);
        }
    });
}

function bindPrescriptionMedicationControls() {
    const container = $("#prescriptionMedications");
    const addButton = $("#addMedicationBtn");

    if (!container || !addButton) return;

    addButton.onclick = () => {
        const index = container.querySelectorAll(".prescription-edit-medication").length;
        container.insertAdjacentHTML("beforeend", prescriptionMedicationFields({}, index));
        bindPrescriptionMedicationControls();
        const newCard = container.querySelector(`[data-medication-index="${index}"] input[name^="name"]`);
        if (newCard) newCard.focus();
    };

    container.querySelectorAll("[data-delete-medication]").forEach((button) => {
        button.onclick = () => {
            const medication = button.closest(".prescription-edit-medication");
            if (medication) {
                medication.remove();
                renumberMedications();
            }
        };
    });
}

function collectPrescriptionMedications() {
    const container = $("#prescriptionMedications");
    if (!container) return [];

    return [...container.querySelectorAll(".prescription-edit-medication")]
        .map((medication) => ({
            name: medication.querySelector('input[name^="name"]')?.value.trim() || "",
            dosage: medication.querySelector('input[name^="dosage"]')?.value.trim() || "",
            frequency: medication.querySelector('input[name^="frequency"]')?.value.trim() || "",
            duration: medication.querySelector('input[name^="duration"]')?.value.trim() || "",
            instructions: medication.querySelector('input[name^="instructions"]')?.value.trim() || "",
        }))
        .filter((medication) => medication.name);
}

function addPrescription(preset = null) {
    const patient = selectedPrescriptionPatient();
    if (!patient) {
        toast(t("selectPatientFirst"));
        return;
    }
    if (window.AERODENT_ONLINE && !canModifyPrescriptions()) return;

    const patientField = window.AERODENT_ONLINE
        ? `<div class="field full-span"><label class="med-label">${t("patient")}</label><input value="${esc(patient.name)}" disabled></div>`
        : `<div class="field full-span"><label class="med-label">${t("patient")}</label><select name="patientId" required><option value="">${t("selectPatient")}</option>${state.patients.map((p) => `<option value="${p.id}" ${p.id === patient.id ? "selected" : ""}>${esc(p.name)} · ${esc(p.phone || "")}</option>`).join("")}</select></div>`;

    const initialRecord = preset ? { medications: [preset] } : null;

    modal(
        t("addPrescription"),
        `<form id="rxForm" class="form-grid">
            ${patientField}
            ${prescriptionForm(initialRecord)}
        </form>`,
    );

    bindPrescriptionMedicationControls();

    $("#rxForm").onsubmit = async (e) => {
        e.preventDefault();
        const data = Object.fromEntries(new FormData(e.target));
        const medications = collectPrescriptionMedications();

        if (!medications.length) {
            toast("At least one medication is required.");
            return;
        }

        if (window.AERODENT_ONLINE) {
            if (selectedPrescriptionPatient()?.id !== patient.id || state.prescriptionSaving) return;
            state.prescriptionSaving = true;
            try {
                const payload = {
                    patient_id: patient.id,
                    date: today(),
                    medications,
                    notes: data.notes || "",
                };
                await window.AERODENT_API.post("/api/prescriptions", payload);
                $("#modal").classList.remove("show");
                await loadOnlinePrescriptions();
                toast(t("savedOnline"));
            } catch (error) {
                toast(prescriptionErrorMessage(error));
            } finally {
                state.prescriptionSaving = false;
            }
            return;
        }

        const offlinePatient = state.patients.find((item) => item.id === Number(data.patientId));
        if (!offlinePatient) return;

        await dbPut("prescriptions", {
            patientId: offlinePatient.id,
            date: today(),
            medications,
            notes: data.notes || "",
        });
        state.selectedPatient = offlinePatient;
        $("#modal").classList.remove("show");
        await refresh();
    };
}

function editPrescription(id) {
    const record = state.prescriptions.find((item) => item.id === id);
    const patient = selectedPrescriptionPatient();
    if (!record || !patient || record.patientId !== patient.id) return;
    if (window.AERODENT_ONLINE && !canModifyPrescriptions()) return;

    modal(t("edit"), `<form id="rxForm" class="form-grid">${prescriptionForm(record)}</form>`);
    bindPrescriptionMedicationControls();

    $("#rxForm").onsubmit = async (e) => {
        e.preventDefault();
        const data = Object.fromEntries(new FormData(e.target));
        const medications = collectPrescriptionMedications();

        if (!medications.length) {
            toast("At least one medication is required.");
            return;
        }

        if (window.AERODENT_ONLINE) {
            if (selectedPrescriptionPatient()?.id !== patient.id || state.prescriptionSaving) return;
            state.prescriptionSaving = true;
            try {
                const payload = {
                    medications,
                    notes: data.notes || "",
                };
                const response = await window.AERODENT_API.patch(`/api/prescriptions/${record.id}`, payload);
                const index = state.prescriptions.findIndex((item) => item.id === record.id);
                if (index !== -1 && selectedPrescriptionPatient()?.id === patient.id) {
                    state.prescriptions[index] = mapApiPrescription(response.data);
                }
                $("#modal").classList.remove("show");
                render();
                toast(t("savedOnline"));
            } catch (error) {
                toast(prescriptionErrorMessage(error));
            } finally {
                state.prescriptionSaving = false;
            }
            return;
        }

        await dbPut("prescriptions", {
            ...record,
            medications,
            notes: data.notes || "",
        });
        $("#modal").classList.remove("show");
        await refresh();
    };
}

async function deletePrescription(id) {
    const record = state.prescriptions.find((item) => item.id === id);
    const patient = selectedPrescriptionPatient();
    if (!record || !patient || record.patientId !== patient.id) return;
    if (window.AERODENT_ONLINE && !canModifyPrescriptions()) return;
    if (!confirm(t("confirmDeleteTreatment") || "Delete this prescription?")) return;

    if (window.AERODENT_ONLINE) {
        if (state.prescriptionSaving) return;
        state.prescriptionSaving = true;
        try {
            await window.AERODENT_API.delete(`/api/prescriptions/${id}`);
            if (selectedPrescriptionPatient()?.id === patient.id) {
                state.prescriptions = state.prescriptions.filter((item) => item.id !== id);
                render();
            }
            toast(t("savedOnline"));
        } catch (error) {
            toast(prescriptionErrorMessage(error));
        } finally {
            state.prescriptionSaving = false;
        }
        return;
    }

    await dbDelete("prescriptions", id);
    await refresh();

    showUndo(t("treatmentDeleted") || "Prescription deleted", async () => {
        await dbPut("prescriptions", record);
        await refresh();
    });
}

function printPrescription(id) {
    state.printPrescriptionId = id;
    document.body.classList.add("printing-prescription");
    render();
    const finish = () => {
        window.onafterprint = null;
        document.body.classList.remove("printing-prescription");
        state.printPrescriptionId = null;
        render();
    };
    if (NativeShell.available) {
        setTimeout(() => printPage(t("prescriptions")).then(finish), 50);
        return;
    }
    window.onafterprint = finish;
    setTimeout(() => window.print(), 50);
}