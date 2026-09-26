const TOOTH_RANGES = {
    permanent: { min: 1, max: 32 },
    primary: { min: 1, max: 20 },
};

let onlineOdontogramRequest = 0;

function mapApiOdontogram(record, patientId) {
    return {
        ...record,
        patientId,
        toothNumber: record.tooth_number,
        toothMode: record.tooth_mode,
        createdBy: record.created_by,
        createdAt: record.created_at,
        updatedAt: record.updated_at,
    };
}

function selectedOdontogramPatient() {
    const patient = state.selectedPatient;
    return Number.isInteger(patient?.id) && patient.id > 0 ? patient : null;
}

function validTooth(mode, number) {
    const range = TOOTH_RANGES[mode];
    return Boolean(range && Number.isInteger(number) && number >= range.min && number <= range.max);
}

function currentToothIdentity() {
    const { toothMode, selectedTooth } = state;
    return validTooth(toothMode, selectedTooth)
        ? { toothMode, toothNumber: selectedTooth }
        : null;
}

function onlineOdontogramError(error) {
    if (error?.status === 0) return t("odontogramNetworkError");
    if (error?.status === 403) return t("readOnly");
    if (error?.status === 404) return t("odontogramUnavailable");
    if (error?.status === 400 || error?.status === 422) {
        return error.message || t("odontogramInvalid");
    }
    return error?.message || t("odontogramUnavailable");
}

function findOdontogramRecord(patientId, toothMode, toothNumber) {
    return state.odontograms.find(
        (item) => item.patientId === patientId
            && item.toothNumber === toothNumber
            && item.toothMode === toothMode,
    );
}

function removeOnlineOdontogram(patientId, toothMode, toothNumber) {
    state.odontograms = state.odontograms.filter(
        (item) => item.patientId !== patientId
            || item.toothNumber !== toothNumber
            || item.toothMode !== toothMode,
    );
}

function upsertOnlineOdontogram(record, patientId) {
    const mapped = mapApiOdontogram(record, patientId);
    const index = state.odontograms.findIndex(
        (item) => item.patientId === mapped.patientId
            && item.toothNumber === mapped.toothNumber
            && item.toothMode === mapped.toothMode,
    );
    if (index === -1) state.odontograms.push(mapped);
    else state.odontograms[index] = mapped;
}

function setOdontogramSaving(isSaving) {
    state.odontogramSaving = isSaving;
    $$("#toothActions .action-btn, #saveToothNote").forEach((element) => {
        element.disabled = isSaving;
    });
}

async function loadOnlineOdontogram() {
    if (!window.AERODENT_ONLINE) return;

    const requestId = ++onlineOdontogramRequest;
    const patient = selectedOdontogramPatient();
    if (!patient) {
        state.odontogramLoading = false;
        state.odontogramReadOnly = false;
        state.odontograms = [];
        state.odontogramError = "";
        render();
        return;
    }

    const patientId = patient.id;
    state.odontogramLoading = true;
    state.odontogramReadOnly = false;
    state.odontogramError = "";
    render();

    try {
        const response = await window.AERODENT_API.get(`/api/patients/${patientId}/odontogram`);
        if (requestId !== onlineOdontogramRequest || selectedOdontogramPatient()?.id !== patientId) return;
        state.odontograms = (response.data || []).map((record) => mapApiOdontogram(record, patientId));
    } catch (error) {
        if (requestId !== onlineOdontogramRequest || selectedOdontogramPatient()?.id !== patientId) return;
        state.odontogramReadOnly = error.status === 403;
        state.odontogramError = onlineOdontogramError(error);
        if (error.status === 404) {
            state.odontograms = state.odontograms.filter((record) => record.patientId !== patientId);
        }
    } finally {
        if (requestId === onlineOdontogramRequest && selectedOdontogramPatient()?.id === patientId) {
            state.odontogramLoading = false;
            render();
        }
    }
}

const TOOTH_SHAPES = {
    incisor: `<svg class="tooth-shape" viewBox="0 0 40 56" xmlns="http://www.w3.org/2000/svg"><path d="M9 4 Q20 -1 31 4 L30 22 Q30 30 20 30 Q10 30 10 22 Z M14 30 Q13 42 17 52 Q20 55 23 52 Q27 42 26 30 Z"/></svg>`,
    canine: `<svg class="tooth-shape" viewBox="0 0 40 56" xmlns="http://www.w3.org/2000/svg"><path d="M20 1 L30 20 Q31 30 20 32 Q9 30 10 20 Z M14 32 Q12 44 17 53 Q20 56 23 53 Q28 44 26 32 Z"/></svg>`,
    premolar: `<svg class="tooth-shape" viewBox="0 0 40 56" xmlns="http://www.w3.org/2000/svg"><path d="M9 8 Q9 1 20 1 Q31 1 31 8 L30 18 Q26 24 20 22 Q14 24 10 18 Z M13 30 Q10 40 14 50 Q17 55 20 52 Q23 55 26 50 Q30 40 27 30 Z"/></svg>`,
    molar: `<svg class="tooth-shape" viewBox="0 0 40 56" xmlns="http://www.w3.org/2000/svg"><path d="M6 8 Q6 0 20 0 Q34 0 34 8 L33 20 Q30 26 24 24 Q20 27 16 24 Q10 26 7 20 Z M10 30 Q7 40 10 50 Q13 55 17 50 Q18 40 18 30 Z M22 30 Q22 40 23 50 Q27 55 30 50 Q33 40 30 30 Z"/></svg>`,
};

function toothShapeType(positionIndex, rowLength) {
    const distance = Math.abs(positionIndex - (rowLength / 2 - 0.5));
    if (rowLength >= 16) {
        if (distance < 2) return "incisor";
        if (distance < 3) return "canine";
        if (distance < 5) return "premolar";
        return "molar";
    }
    if (distance < 2) return "incisor";
    if (distance < 3) return "canine";
    return "molar";
}

function renderOdontogram() {
    const primary = state.toothMode === "primary";
    const patient = state.selectedPatient;
    const patientOptions = state.patients.map((item) => `<option value="${item.id}" ${item.id === patient?.id ? "selected" : ""}>${esc(item.name)} · ${esc(item.phone || "")}</option>`).join("");
    const upperCount = primary ? 10 : 16;
    const lowerCount = primary ? 10 : 16;
    const status = !patient
        ? `<p class="muted">${t("noPatient")}</p>`
        : state.odontogramLoading
            ? `<p class="muted">${t("loading")}</p>`
            : state.odontogramError
                ? `<p class="login-error">${esc(state.odontogramError)}</p>`
                : "";
    return `<section class="card workspace-card"><div class="workspace-toolbar"><div><div class="eyebrow">${t("odontogram")}</div><h2>${patient ? esc(patient.name) : t("selectPatient")}</h2><div class="field odontogram-patient-picker"><label>${t("patient")}</label><select id="odontogramPatientSelect"><option value="">${t("selectPatient")}</option>${patientOptions}</select></div></div><div class="segmented"><button class="${!primary ? "active" : ""}" data-mode="permanent">${t("permanent")}</button><button class="${primary ? "active" : ""}" data-mode="primary">${t("primary")}</button></div></div><div class="odontogram-wrap ${primary ? "primary-odontogram" : ""}">${status}<div class="arch-title">${t("maxillary")}</div><div class="odontogram-direction-labels"><span class="right">${t("right")}</span><span class="left">${t("left")}</span></div><div class="teeth-row">${Array.from({ length: upperCount }, (_, index) => tooth(index + 1, index, upperCount)).join("")}</div><div class="arch-title" style="margin-top:26px">${t("mandibular")}</div><div class="teeth-row">${Array.from({ length: lowerCount }, (_, index) => tooth(primary ? index + 11 : index + 17, index, lowerCount)).join("")}</div><div class="legend">${[["healthy", "healthy"], ["decay", "decay"], ["filling", "filling"], ["crown", "crown"], ["rct", "rct"], ["extract", "extract"], ["implant", "implant"]].map(([color, key]) => `<span><i style="background:var(--${color === "healthy" ? "surface" : color})"></i>${t(key)}</span>`).join("")}</div></div></section>`;
}

function tooth(number, positionIndex, rowLength) {
    const primary = state.toothMode === "primary";
    const patient = state.selectedPatient;
    const record = findOdontogramRecord(patient?.id, state.toothMode, number);
    const condition = record?.condition || "healthy";
    const label = primary ? String.fromCharCode(64 + number) : number;
    return `<button class="tooth ${primary ? "primary-tooth " : ""}${condition}" data-tooth="${number}" title="${t("tooth")} ${label}" ${patient ? "" : "disabled"}><span class="tooth-visual">${TOOTH_SHAPES[toothShapeType(positionIndex, rowLength)]}<span class="tooth-mark"></span></span><span class="tooth-label">${label}</span></button>`;
}

async function openTooth(number) {
    const patient = selectedOdontogramPatient();
    if (!patient || !validTooth(state.toothMode, number)) {
        toast(patient ? t("odontogramInvalid") : t("selectPatientFirst"));
        return;
    }
    state.selectedTooth = number;
    const record = findOdontogramRecord(patient.id, state.toothMode, number);
    $("#drawerTooth").textContent = `#${number}`;
    $("#drawerAnatomy").textContent = currentLanguage === "ar" ? "رحى علوية / سفلية" : "Molar · clinical surface";
    const readOnly = window.AERODENT_ONLINE
        && (!hasPermission("odontogram.update") || state.odontogramReadOnly);
    if (readOnly) {
        $("#toothActions").innerHTML = `<p class="muted">${t("readOnly")}</p>`;
    } else {
        $("#toothActions").innerHTML = PROCEDURES.map(([key, label]) => `<button class="action-btn ${record?.condition === key ? "active" : ""}" data-procedure="${key}">${t(label)}</button>`).join("");
        $$(".action-btn").forEach((button) => (button.onclick = () => updateTooth(button.dataset.procedure)));
    }
    $("#toothNote").value = record?.notes || "";
    $("#toothNote").disabled = readOnly;
    $("#saveToothNote").hidden = readOnly;
    setOdontogramSaving(state.odontogramSaving);
    document.body.classList.add("drawer-open");
}

async function updateTooth(condition) {
    const patient = selectedOdontogramPatient();
    const identity = currentToothIdentity();
    if (!patient || !identity) {
        toast(patient ? t("odontogramInvalid") : t("selectPatientFirst"));
        return;
    }
    if (window.AERODENT_ONLINE) {
        if (!hasPermission("odontogram.update") || state.odontogramReadOnly || state.odontogramSaving) return;
        setOdontogramSaving(true);
        const existing = findOdontogramRecord(patient.id, identity.toothMode, identity.toothNumber);
        let saved = false;
        let forbidden = false;
        try {
            const url = `/api/patients/${patient.id}/odontogram/${identity.toothMode}/${identity.toothNumber}`;
            if (condition === "clear") {
                await window.AERODENT_API.delete(url);
                if (selectedOdontogramPatient()?.id === patient.id) {
                    removeOnlineOdontogram(patient.id, identity.toothMode, identity.toothNumber);
                }
            } else {
                const response = await window.AERODENT_API.put(url, { condition, procedure: t(condition), notes: existing?.notes || null });
                if (selectedOdontogramPatient()?.id === patient.id) {
                    upsertOnlineOdontogram(response.data, patient.id);
                }
            }
            if (selectedOdontogramPatient()?.id === patient.id) state.odontogramError = "";
            saved = true;
            toast(t("savedOnline"));
        } catch (error) {
            if (error.status === 404 && error.payload?.error === "Odontogram record not found.") {
                if (selectedOdontogramPatient()?.id === patient.id) {
                    removeOnlineOdontogram(patient.id, identity.toothMode, identity.toothNumber);
                }
                saved = true;
            } else {
                if (selectedOdontogramPatient()?.id === patient.id) {
                    state.odontogramReadOnly = error.status === 403;
                    forbidden = error.status === 403;
                    state.odontogramError = onlineOdontogramError(error);
                    if (error.status === 404) {
                        state.odontograms = state.odontograms.filter((record) => record.patientId !== patient.id);
                    }
                    toast(state.odontogramError);
                }
            }
        } finally {
            setOdontogramSaving(false);
            if (saved && selectedOdontogramPatient()?.id === patient.id) {
                render();
                openTooth(identity.toothNumber);
            } else if (forbidden && selectedOdontogramPatient()?.id === patient.id) {
                render();
                openTooth(identity.toothNumber);
            }
        }
        return;
    }
    const existing = findOdontogramRecord(patient.id, identity.toothMode, identity.toothNumber);
    if (condition === "clear") {
        if (existing) await dbDelete("odontograms", existing.id);
    } else {
        await dbPut("odontograms", { ...(existing || {}), patientId: patient.id, toothNumber: identity.toothNumber, toothMode: identity.toothMode, condition, procedure: t(condition), timestamp: new Date().toISOString() });
    }
    await refresh();
    openTooth(state.selectedTooth);
}

async function saveCurrentToothNote() {
    const patient = selectedOdontogramPatient();
    const identity = currentToothIdentity();
    if (!patient || !identity) {
        toast(patient ? t("odontogramInvalid") : t("selectPatientFirst"));
        return;
    }
    const existing = findOdontogramRecord(patient.id, identity.toothMode, identity.toothNumber);
    if (window.AERODENT_ONLINE) {
        if (!hasPermission("odontogram.update") || state.odontogramReadOnly || state.odontogramSaving) return;
        setOdontogramSaving(true);
        let saved = false;
        let forbidden = false;
        try {
            const response = await window.AERODENT_API.put(`/api/patients/${patient.id}/odontogram/${identity.toothMode}/${identity.toothNumber}`, { condition: existing?.condition || "healthy", procedure: existing?.procedure || null, notes: $("#toothNote").value });
            if (selectedOdontogramPatient()?.id === patient.id) {
                upsertOnlineOdontogram(response.data, patient.id);
                state.odontogramError = "";
            }
            saved = true;
            toast(t("savedOnline"));
        } catch (error) {
            if (selectedOdontogramPatient()?.id === patient.id) {
                state.odontogramReadOnly = error.status === 403;
                forbidden = error.status === 403;
                state.odontogramError = onlineOdontogramError(error);
                if (error.status === 404) {
                    state.odontograms = state.odontograms.filter((record) => record.patientId !== patient.id);
                }
                toast(state.odontogramError);
            }
        } finally {
            setOdontogramSaving(false);
            if (saved && selectedOdontogramPatient()?.id === patient.id) {
                render();
                openTooth(identity.toothNumber);
            } else if (forbidden && selectedOdontogramPatient()?.id === patient.id) {
                render();
                openTooth(identity.toothNumber);
            }
        }
        return;
    }
    await dbPut("odontograms", { ...(existing || {}), patientId: patient.id, toothNumber: identity.toothNumber, toothMode: identity.toothMode, condition: existing?.condition || "healthy", notes: $("#toothNote").value, timestamp: new Date().toISOString() });
    toast(t("saved"));
    state.odontograms = await dbGetAll("odontograms");
}
