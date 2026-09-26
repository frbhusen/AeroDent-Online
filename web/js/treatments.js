let onlineTreatmentRequest = 0;
let onlineInvoiceRequest = 0;

function mapApiTreatment(treatment) {
    return {
        ...treatment,
        clinicId: treatment.clinic_id,
        patientId: treatment.patient_id,
        doctorId: treatment.doctor_id,
        toothNumber: treatment.tooth_number,
        createdBy: treatment.created_by,
        createdAt: treatment.created_at,
        updatedAt: treatment.updated_at,
    };
}

function mapApiInvoice(invoice) {
    return {
        ...invoice,
        clinicId: invoice.clinic_id,
        patientId: invoice.patient_id,
        treatmentId: invoice.treatment_id,
        paidAmount: invoice.paid_amount,
        createdBy: invoice.created_by,
        createdAt: invoice.created_at,
        updatedAt: invoice.updated_at,
    };
}

function selectedTreatmentPatient() {
    const patient = state.selectedPatient;
    return Number.isInteger(patient?.id) && patient.id > 0 ? patient : null;
}

function canModifyTreatments() {
    return !window.AERODENT_ONLINE || (
        !state.treatmentReadOnly
        && hasPermission("treatments.create")
        && hasPermission("treatments.update")
        && hasPermission("treatments.delete")
    );
}

function canCreateInvoices() {
    return !window.AERODENT_ONLINE || hasPermission("invoices.create");
}

function canUpdateInvoices() {
    return !window.AERODENT_ONLINE || hasPermission("invoices.update");
}

function canDeleteInvoices() {
    return !window.AERODENT_ONLINE || hasPermission("invoices.delete");
}

function treatmentErrorMessage(error) {
    if (error?.status === 0) return t("treatmentNetworkError");
    if (error?.status === 403) return t("readOnly");
    if (error?.status === 404) return t("treatmentUnavailable");
    if (error?.status === 409) return error.message || t("treatmentConflict");
    if (error?.status === 400 || error?.status === 422) return error.message || t("treatmentInvalid");
    return error?.message || t("treatmentUnavailable");
}

function invoiceErrorMessage(error) {
    if (error?.status === 0) return t("treatmentNetworkError");
    if (error?.status === 403) return t("readOnly");
    if (error?.status === 404) return t("invoiceUnavailable") || "Invoice not found";
    return error?.message || "Invoice request failed";
}

function setTreatmentSaving(isSaving) {
    state.treatmentSaving = isSaving;
    $$("#treatmentForm button[type=submit], #editTreatmentForm button[type=submit], .treatment-status-select").forEach((element) => {
        element.disabled = isSaving;
    });
}

function setInvoiceSaving(isSaving) {
    state.invoiceSaving = isSaving;
    $$("#invoiceForm button[type=submit], #editInvoiceForm button[type=submit]").forEach((element) => {
        element.disabled = isSaving;
    });
}

function treatmentPagination() {
    if (!window.AERODENT_ONLINE || state.treatmentPages <= 1) return "";
    return `<div class="patient-pagination"><button class="button button-ghost" data-treatment-page="previous" ${state.treatmentPage <= 1 ? "disabled" : ""}>${t("previous")}</button><span>${state.treatmentPage} / ${state.treatmentPages}</span><button class="button button-ghost" data-treatment-page="next" ${state.treatmentPage >= state.treatmentPages ? "disabled" : ""}>${t("next")}</button></div>`;
}

function invoicePagination() {
    if (!window.AERODENT_ONLINE || state.invoicePages <= 1) return "";
    return `<div class="patient-pagination"><button class="button button-ghost" data-invoice-page="previous" ${state.invoicePage <= 1 ? "disabled" : ""}>${t("previous")}</button><span>${state.invoicePage} / ${state.invoicePages}</span><button class="button button-ghost" data-invoice-page="next" ${state.invoicePage >= state.invoicePages ? "disabled" : ""}>${t("next")}</button></div>`;
}

function treatmentRows(items, editable) {
    if (state.treatmentLoading) return `<tr><td colspan="6" class="muted">${t("loading")}</td></tr>`;
    if (state.treatmentError) return `<tr><td colspan="6" class="login-error">${esc(state.treatmentError)}</td></tr>`;
    if (!items.length) return `<tr><td colspan="6" class="muted">${t("noTreatments")}</td></tr>`;
    return items.map((item) => `<tr><td>#${item.toothNumber || "—"}</td><td>${esc(item.description)}</td><td>${esc(item.date)}</td><td>${money(item.fee)}</td><td>${editable ? `<select class="treatment-status-select" data-treatment-status="${item.id}"><option value="planned" ${item.status === "planned" ? "selected" : ""}>${t("planned")}</option><option value="accepted" ${item.status === "accepted" ? "selected" : ""}>${t("accepted")}</option><option value="scheduled" ${item.status === "scheduled" ? "selected" : ""}>${t("scheduled")}</option><option value="in-progress" ${item.status === "in-progress" ? "selected" : ""}>${t("inProgress")}</option><option value="completed" ${item.status === "completed" ? "selected" : ""}>${t("completed")}</option><option value="cancelled" ${item.status === "cancelled" ? "selected" : ""}>${t("cancelled")}</option></select>` : esc(t(item.status || "planned"))}</td><td>${editable ? `<button type="button" class="button button-ghost" data-edit-treatment="${item.id}">${t("edit")}</button><button type="button" class="button btn-danger-ghost" data-delete-treatment="${item.id}" title="${t("delete")}" aria-label="${t("delete")}">×</button>` : ""}</td></tr>`).join("");
}

function invoiceRows(items) {
    if (state.invoiceLoading) return `<tr><td colspan="7" class="muted">${t("loading")}</td></tr>`;
    if (state.invoiceError) return `<tr><td colspan="7" class="login-error">${esc(state.invoiceError)}</td></tr>`;
    if (!items.length) return `<tr><td colspan="7" class="muted">${t("noInvoices")}</td></tr>`;
    
    const canEdit = canUpdateInvoices();
    const canDelete = canDeleteInvoices();

    return items.map((item) => {
        const dateStr = item.createdAt ? item.createdAt.slice(0, 10) : today();
        const statusBadge = `<span class="badge ${item.status === 'paid' ? 'badge-green' : item.status === 'partially-paid' ? 'badge-blue' : item.status === 'cancelled' ? 'badge-gray' : 'badge-amber'}">${t(item.status || "unpaid")}</span>`;
        const actions = [];
        if (canEdit && item.status !== "paid" && Number(item.balance || 0) > 0) {
            actions.push(`<button type="button" class="button button-sm button-primary" data-add-payment="${item.id}" title="${t("addPayment")}">+ ${t("addPayment")}</button>`);
        }
        if (canEdit) actions.push(`<button type="button" class="button button-ghost button-sm" data-edit-invoice="${item.id}">${t("edit")}</button>`);
        if (canDelete) actions.push(`<button type="button" class="button button-sm btn-danger-ghost" data-delete-invoice="${item.id}" title="${t("delete")}" aria-label="${t("delete")}">×</button>`);

        return `<tr>
            <td>${esc(dateStr)}</td>
            <td>${money(item.amount)}</td>
            <td>${money(item.discount || 0)}</td>
            <td>${money(item.paidAmount || item.paid_amount || 0)}</td>
            <td><strong>${money(item.balance)}</strong></td>
            <td>${statusBadge}</td>
            <td>${actions.join(" ")}</td>
        </tr>`;
    }).join("");
}

function renderTreatments() {
    const patient = selectedTreatmentPatient();
    const items = window.AERODENT_ONLINE ? state.treatments : state.treatments.filter((item) => item.patientId === patient?.id);
    const invoiceItems = window.AERODENT_ONLINE ? state.invoices : state.invoices.filter((item) => item.patientId === patient?.id);
    const currentTreatmentTotal = items.reduce((sum, item) => sum + Number(item.fee || 0), 0);
    const totalBalance = invoiceItems.reduce((sum, item) => sum + Number(item.balance || 0), 0);

    const patientOptions = state.patients.map((item) => `<option value="${item.id}" ${item.id === patient?.id ? "selected" : ""}>${esc(item.name)} · ${esc(item.phone || "")}</option>`).join("");
    const editable = patient && canModifyTreatments();
    const readOnly = window.AERODENT_ONLINE && patient && !editable ? `<p class="muted">${t("readOnly")}</p>` : "";

    const treatmentTotalLabel = (window.AERODENT_ONLINE && state.treatmentPages > 1)
        ? `${t("invoiceTotal")} (${t("currentPage")})`
        : t("invoiceTotal");

    return `<section class="content-grid treatments-billing-layout">
        <div class="card">
            <div class="card-heading">
                <h2>${t("treatments")}</h2>
                ${editable ? `<button class="button button-primary" data-action="addTreatment">＋ ${t("addTreatment")}</button>` : ""}
            </div>
            <div class="field treatment-patient-picker">
                <label>${t("patient")}</label>
                <select id="treatmentPatientSelect">
                    <option value="">${t("selectPatient")}</option>
                    ${patientOptions}
                </select>
            </div>
            ${readOnly}
            <div class="table-wrap">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>${t("tooth")}</th>
                            <th>${t("procedure")}</th>
                            <th>${t("date")}</th>
                            <th>${t("fee")}</th>
                            <th>${t("status")}</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        ${patient ? treatmentRows(items, editable) : `<tr><td colspan="6" class="muted">${t("noPatient")}</td></tr>`}
                    </tbody>
                </table>
            </div>
            ${treatmentPagination()}
            <div class="form-actions" style="margin-top: 12px; justify-content: flex-end;">
                <span class="muted">${treatmentTotalLabel}:</span>
                <strong>${money(currentTreatmentTotal)}</strong>
            </div>
        </div>

        <div class="card invoice-print">
            <div class="card-heading">
                <h2>${t("invoices")}</h2>
                <div style="display: flex; gap: 8px;">
                    ${canCreateInvoices() && patient ? `<button class="button button-primary" data-action="addInvoice">＋ ${t("addInvoice")}</button>` : ""}
                    <button class="button button-ghost" data-print-invoices>⌁ ${t("print")}</button>
                </div>
            </div>
            <div class="patient-summary">
                <div>
                    <h3>${esc(patient?.name || t("selectPatient"))}</h3>
                    <p>${t("invoice")} · ${today()}</p>
                </div>
                <span class="badge badge-blue">${esc(state.settings?.currencySymbol || "SYR")}</span>
            </div>
            
            <div class="table-wrap" style="margin-top: 12px;">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>${t("date")}</th>
                            <th>${t("amount")}</th>
                            <th>${t("discount")}</th>
                            <th>${t("paidAmount")}</th>
                            <th>${t("balance")}</th>
                            <th>${t("status")}</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        ${patient ? invoiceRows(invoiceItems) : `<tr><td colspan="7" class="muted">${t("noPatient")}</td></tr>`}
                    </tbody>
                </table>
            </div>
            ${invoicePagination()}

            <div class="form-actions" style="margin-top: 16px; border-top: 1px solid var(--border); padding-top: 12px;">
                <span class="muted">${t("outstanding")}:</span>
                <strong style="color: var(--danger, #ef4444);">${money(totalBalance)}</strong>
            </div>
        </div>
    </section>`;
}

async function loadOnlineTreatments() {
    if (!window.AERODENT_ONLINE) return;
    const requestId = ++onlineTreatmentRequest;
    const patient = selectedTreatmentPatient();
    if (!patient) {
        state.treatmentLoading = false;
        state.treatmentReadOnly = false;
        state.treatments = [];
        state.treatmentError = "";
        render();
        return;
    }

    const patientId = patient.id;
    state.treatmentLoading = true;
    state.treatmentReadOnly = false;
    state.treatmentError = "";
    render();
    try {
        const params = new URLSearchParams({
            patient_id: String(patientId),
            page: String(state.treatmentPage),
            per_page: String(state.treatmentPerPage),
        });
        const response = await window.AERODENT_API.get(`/api/treatments?${params}`);
        if (requestId !== onlineTreatmentRequest || selectedTreatmentPatient()?.id !== patientId) return;
        state.treatments = (response.data || []).map(mapApiTreatment);
        state.treatmentTotal = response.meta?.total || 0;
        state.treatmentPages = response.meta?.pages || 0;
    } catch (error) {
        if (requestId !== onlineTreatmentRequest || selectedTreatmentPatient()?.id !== patientId) return;
        state.treatmentReadOnly = error.status === 403;
        state.treatmentError = treatmentErrorMessage(error);
        if (error.status === 404) state.treatments = [];
    } finally {
        if (requestId === onlineTreatmentRequest && selectedTreatmentPatient()?.id === patientId) {
            state.treatmentLoading = false;
            render();
        }
    }
}

async function loadOnlineInvoices() {
    if (!window.AERODENT_ONLINE) return;
    const requestId = ++onlineInvoiceRequest;
    const patient = selectedTreatmentPatient();
    if (!patient) {
        state.invoiceLoading = false;
        state.invoices = [];
        state.invoiceError = "";
        render();
        return;
    }

    const patientId = patient.id;
    state.invoiceLoading = true;
    state.invoiceError = "";
    render();
    try {
        const params = new URLSearchParams({
            patient_id: String(patientId),
            page: String(state.invoicePage),
            per_page: String(state.invoicePerPage),
        });
        const response = await window.AERODENT_API.get(`/api/invoices?${params}`);
        if (requestId !== onlineInvoiceRequest || selectedTreatmentPatient()?.id !== patientId) return;
        state.invoices = (response.data || []).map(mapApiInvoice);
        state.invoiceTotal = response.meta?.total || 0;
        state.invoicePages = response.meta?.pages || 0;
    } catch (error) {
        if (requestId !== onlineInvoiceRequest || selectedTreatmentPatient()?.id !== patientId) return;
        state.invoiceError = invoiceErrorMessage(error);
        if (error.status === 404) state.invoices = [];
    } finally {
        if (requestId === onlineInvoiceRequest && selectedTreatmentPatient()?.id === patientId) {
            state.invoiceLoading = false;
            render();
        }
    }
}

function handleOnlineTreatmentPatientChange() {
    if (!window.AERODENT_ONLINE) return;
    ++onlineTreatmentRequest;
    ++onlineInvoiceRequest;
    state.treatmentPage = 1;
    state.treatments = [];
    state.treatmentError = "";
    state.invoicePage = 1;
    state.invoices = [];
    state.invoiceError = "";
    if (state.view === "treatments") {
        loadOnlineTreatments();
        loadOnlineInvoices();
    }
}

function treatmentPayload(data, patientId) {
    return {
        patient_id: patientId,
        tooth_number: data.toothNumber === "" || data.toothNumber == null ? null : Number(data.toothNumber),
        status: data.status || "planned",
        fee: data.fee || "0",
        description: data.description,
        date: today(),
    };
}

function addTreatment() {
    const patient = selectedTreatmentPatient();
    if (!patient) {
        toast(t("selectPatientFirst"));
        return;
    }
    if (window.AERODENT_ONLINE && !canModifyTreatments()) return;

    const patientField = window.AERODENT_ONLINE
        ? `<div class="field full-span"><label>${t("patient")}</label><input value="${esc(patient.name)}" disabled></div>`
        : `<div class="field full-span"><label>${t("patient")}</label><select name="patientId" required><option value="">${t("selectPatient")}</option>${state.patients.map((item) => `<option value="${item.id}" ${item.id === patient.id ? "selected" : ""}>${esc(item.name)} · ${esc(item.phone || "")}</option>`).join("")}</select></div>`;
    modal(t("addTreatment"), `<form id="treatmentForm" class="form-grid">${patientField}<div class="field"><label>${t("tooth")}</label><input type="number" name="toothNumber" min="1" max="32"></div><div class="field"><label>${t("status")}</label><select name="status"><option value="planned">${t("planned")}</option><option value="accepted">${t("accepted")}</option><option value="scheduled">${t("scheduled")}</option><option value="in-progress">${t("inProgress")}</option><option value="completed">${t("completed")}</option><option value="cancelled">${t("cancelled")}</option></select></div><div class="field"><label>${t("fee")}</label><input type="number" name="fee" min="0" step="0.01" value="0"></div><div class="field full-span"><label>${t("procedure")}</label><input name="description" required></div><div class="form-actions full-span"><button type="submit" class="button button-primary">${t("save")}</button></div></form>`);

    $("#treatmentForm").onsubmit = async (event) => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(event.target));
        if (window.AERODENT_ONLINE) {
            if (selectedTreatmentPatient()?.id !== patient.id || state.treatmentSaving) return;
            setTreatmentSaving(true);
            try {
                await window.AERODENT_API.post("/api/treatments", treatmentPayload(data, patient.id));
                $("#modal").classList.remove("show");
                state.treatmentPage = 1;
                await loadOnlineTreatments();
                toast(t("savedOnline"));
            } catch (error) {
                state.treatmentError = treatmentErrorMessage(error);
                state.treatmentReadOnly = error.status === 403;
                toast(state.treatmentError);
            } finally {
                setTreatmentSaving(false);
            }
            return;
        }

        const offlinePatient = state.patients.find((item) => item.id === Number(data.patientId));
        if (!offlinePatient) return;
        await dbPut("treatments", { ...data, patientId: offlinePatient.id, toothNumber: Number(data.toothNumber) || null, fee: Number(data.fee) || 0, status: data.status || "planned", date: today() });
        $("#modal").classList.remove("show");
        await refresh();
    };
}

function editTreatment(id) {
    const treatment = state.treatments.find((item) => item.id === id);
    const patient = selectedTreatmentPatient();
    if (!treatment || !patient || treatment.patientId !== patient.id) return;
    if (window.AERODENT_ONLINE && !canModifyTreatments()) return;

    modal(t("edit"), `<form id="editTreatmentForm" class="form-grid"><div class="field"><label>${t("tooth")}</label><input type="number" name="toothNumber" min="1" max="32" value="${esc(treatment.toothNumber || "")}"></div><div class="field"><label>${t("fee")}</label><input type="number" name="fee" min="0" step="0.01" value="${esc(treatment.fee || "0")}"></div><div class="field full-span"><label>${t("procedure")}</label><input name="description" required value="${esc(treatment.description || "")}"></div><div class="form-actions full-span"><button class="button button-primary" type="submit">${t("save")}</button></div></form>`);
    $("#editTreatmentForm").onsubmit = async (event) => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(event.target));
        if (window.AERODENT_ONLINE) {
            if (selectedTreatmentPatient()?.id !== patient.id || state.treatmentSaving) return;
            setTreatmentSaving(true);
            try {
                const response = await window.AERODENT_API.patch(`/api/treatments/${treatment.id}`, { tooth_number: data.toothNumber === "" ? null : Number(data.toothNumber), description: data.description, fee: data.fee || "0" });
                const index = state.treatments.findIndex((item) => item.id === treatment.id);
                if (index !== -1 && selectedTreatmentPatient()?.id === patient.id) state.treatments[index] = mapApiTreatment(response.data);
                $("#modal").classList.remove("show");
                render();
                toast(t("savedOnline"));
            } catch (error) {
                state.treatmentError = treatmentErrorMessage(error);
                state.treatmentReadOnly = error.status === 403;
                toast(state.treatmentError);
            } finally {
                setTreatmentSaving(false);
            }
            return;
        }

        await dbPut("treatments", { ...treatment, toothNumber: Number(data.toothNumber) || null, description: data.description, fee: Number(data.fee) || 0 });
        $("#modal").classList.remove("show");
        await refresh();
    };
}

async function deleteTreatment(id) {
    const treatment = state.treatments.find((item) => item.id === id);
    const patient = selectedTreatmentPatient();
    if (!treatment || !patient || treatment.patientId !== patient.id) return;
    if (window.AERODENT_ONLINE && !canModifyTreatments()) return;
    if (!confirm(t("confirmDeleteTreatment"))) return;

    if (window.AERODENT_ONLINE) {
        if (state.treatmentSaving) return;
        setTreatmentSaving(true);
        try {
            await window.AERODENT_API.delete(`/api/treatments/${id}`);
            if (selectedTreatmentPatient()?.id === patient.id) {
                state.treatments = state.treatments.filter((item) => item.id !== id);
                state.treatmentTotal = Math.max(0, state.treatmentTotal - 1);
                if (!state.treatments.length && state.treatmentPage > 1) state.treatmentPage -= 1;
                await loadOnlineTreatments();
            }
            toast(t("treatmentDeleted"));
        } catch (error) {
            state.treatmentError = treatmentErrorMessage(error);
            state.treatmentReadOnly = error.status === 403;
            toast(state.treatmentError);
        } finally {
            setTreatmentSaving(false);
        }
        return;
    }

    await dbDelete("treatments", id);
    await refresh();
    showUndo(t("treatmentDeleted"), async () => {
        await dbPut("treatments", treatment);
        await refresh();
    });
}

function addInvoice() {
    const patient = selectedTreatmentPatient();
    if (!patient) {
        toast(t("selectPatientFirst"));
        return;
    }
    if (!canCreateInvoices()) return;

    const availableTreatments = state.treatments.map((tr) =>
        `<option value="${tr.id}">${tr.toothNumber ? `#${tr.toothNumber} ` : ""}${esc(tr.description)} (${money(tr.fee)})</option>`
    ).join("");

    modal(t("addInvoice"), `
        <form id="invoiceForm" class="form-grid">
            <div class="field full-span">
                <label>${t("patient")}</label>
                <input value="${esc(patient.name)}" disabled>
            </div>
            <div class="field full-span">
                <label>${t("treatment")}</label>
                <select name="treatmentId">
                    <option value="">-- ${t("generalVisit")} --</option>
                    ${availableTreatments}
                </select>
            </div>
            <div class="field">
                <label>${t("amount")}</label>
                <input type="number" name="amount" min="0" step="0.01" required value="0">
            </div>
            <div class="field">
                <label>${t("discount")}</label>
                <input type="number" name="discount" min="0" step="0.01" value="0">
            </div>
            <div class="field full-span">
                <label>${t("paidAmount")}</label>
                <input type="number" name="paidAmount" min="0" step="0.01" value="0">
            </div>
            <div class="form-actions full-span">
                <button class="button button-primary" type="submit">${t("save")}</button>
            </div>
        </form>
    `);

    $("#invoiceForm").onsubmit = async (event) => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(event.target));
        if (window.AERODENT_ONLINE) {
            if (selectedTreatmentPatient()?.id !== patient.id || state.invoiceSaving) return;
            setInvoiceSaving(true);
            try {
                await window.AERODENT_API.post("/api/invoices", {
                    patient_id: patient.id,
                    treatment_id: data.treatmentId ? Number(data.treatmentId) : null,
                    amount: data.amount || "0",
                    discount: data.discount || "0",
                    paid_amount: data.paidAmount || "0",
                });
                $("#modal").classList.remove("show");
                state.invoicePage = 1;
                await loadOnlineInvoices();
                toast(t("savedOnline"));
            } catch (error) {
                toast(invoiceErrorMessage(error));
            } finally {
                setInvoiceSaving(false);
            }
            return;
        }

        const amt = Number(data.amount) || 0;
        const disc = Number(data.discount) || 0;
        const paid = Number(data.paidAmount) || 0;
        const payable = Math.max(0, amt - disc);
        const bal = Math.max(0, payable - paid);
        const st = paid >= payable ? "paid" : paid > 0 ? "partially-paid" : "unpaid";

        await dbPut("invoices", {
            patientId: patient.id,
            treatmentId: data.treatmentId ? Number(data.treatmentId) : null,
            amount: amt,
            discount: disc,
            paidAmount: paid,
            balance: bal,
            status: st,
            createdAt: today(),
        });
        $("#modal").classList.remove("show");
        await refresh();
    };
}

function editInvoice(id) {
    const invoice = state.invoices.find((item) => item.id === id);
    const patient = selectedTreatmentPatient();
    if (!invoice || !patient || invoice.patientId !== patient.id) return;
    if (!canUpdateInvoices()) return;

    modal(t("editInvoice"), `
        <form id="editInvoiceForm" class="form-grid">
            <div class="field full-span">
                <label>${t("patient")}</label>
                <input value="${esc(patient.name)}" disabled>
            </div>
            <div class="field">
                <label>${t("amount")}</label>
                <input type="number" name="amount" min="0" step="0.01" value="${esc(invoice.amount)}" required>
            </div>
            <div class="field">
                <label>${t("discount")}</label>
                <input type="number" name="discount" min="0" step="0.01" value="${esc(invoice.discount || "0")}">
            </div>
            <div class="field">
                <label>${t("paidAmount")}</label>
                <input type="number" name="paidAmount" min="0" step="0.01" value="${esc(invoice.paidAmount || invoice.paid_amount || "0")}">
            </div>
            <div class="field">
                <label>${t("status")}</label>
                <select name="status">
                    <option value="unpaid" ${invoice.status === "unpaid" ? "selected" : ""}>${t("unpaid")}</option>
                    <option value="partially-paid" ${invoice.status === "partially-paid" ? "selected" : ""}>${t("partially-paid")}</option>
                    <option value="paid" ${invoice.status === "paid" ? "selected" : ""}>${t("paid")}</option>
                    <option value="cancelled" ${invoice.status === "cancelled" ? "selected" : ""}>${t("cancelled")}</option>
                </select>
            </div>
            <div class="form-actions full-span">
                <button class="button button-primary" type="submit">${t("save")}</button>
            </div>
        </form>
    `);

    $("#editInvoiceForm").onsubmit = async (event) => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(event.target));
        if (window.AERODENT_ONLINE) {
            if (selectedTreatmentPatient()?.id !== patient.id || state.invoiceSaving) return;
            setInvoiceSaving(true);
            try {
                await window.AERODENT_API.patch(`/api/invoices/${invoice.id}`, {
                    amount: data.amount,
                    discount: data.discount || "0",
                    paid_amount: data.paidAmount || "0",
                    status: data.status,
                });
                $("#modal").classList.remove("show");
                await loadOnlineInvoices();
                toast(t("savedOnline"));
            } catch (error) {
                toast(invoiceErrorMessage(error));
            } finally {
                setInvoiceSaving(false);
            }
            return;
        }

        const amt = Number(data.amount) || 0;
        const disc = Number(data.discount) || 0;
        const paid = Number(data.paidAmount) || 0;
        const payable = Math.max(0, amt - disc);
        const bal = Math.max(0, payable - paid);

        await dbPut("invoices", {
            ...invoice,
            amount: amt,
            discount: disc,
            paidAmount: paid,
            balance: bal,
            status: data.status || invoice.status,
        });
        $("#modal").classList.remove("show");
        await refresh();
    };
}

async function deleteInvoice(id) {
    const invoice = state.invoices.find((item) => item.id === id);
    const patient = selectedTreatmentPatient();
    if (!invoice || !patient || invoice.patientId !== patient.id) return;
    if (!canDeleteInvoices()) return;
    if (!confirm(t("confirmDeleteInvoice"))) return;

    if (window.AERODENT_ONLINE) {
        if (state.invoiceSaving) return;
        setInvoiceSaving(true);
        try {
            await window.AERODENT_API.delete(`/api/invoices/${id}`);
            toast(t("invoiceDeleted"));
            state.invoices = state.invoices.filter((item) => item.id !== id);
            state.invoiceTotal = Math.max(0, state.invoiceTotal - 1);
            if (!state.invoices.length && state.invoicePage > 1) state.invoicePage -= 1;
            await loadOnlineInvoices();
        } catch (error) {
            toast(invoiceErrorMessage(error));
        } finally {
            setInvoiceSaving(false);
        }
        return;
    }

    await dbDelete("invoices", id);
    await refresh();
    toast(t("invoiceDeleted"));
}

function openAddPaymentModal(invoiceId) {
    const inv = state.invoices.find((item) => item.id === invoiceId);
    if (!inv) return;
    const balance = Number(inv.balance || 0);

    modal(`${t("addPayment")} - #${inv.id}`, `
        <form id="addPaymentForm" class="form-grid">
            <div class="field full-span">
                <label>${t("balanceDue")}</label>
                <div style="font-size:18px;font-weight:700;color:var(--primary);">${money(balance)}</div>
            </div>
            <div class="field">
                <label>${t("paymentAmount")}</label>
                <input name="amount" type="number" step="0.01" min="0.01" max="${balance}" value="${balance}" required>
            </div>
            <div class="field">
                <label>${t("paymentMethod")}</label>
                <select name="payment_method">
                    <option value="cash">Cash (نقدي)</option>
                    <option value="card">Card (بطاقة)</option>
                    <option value="bank_transfer">Bank Transfer (تحويل)</option>
                    <option value="other">Other (أخرى)</option>
                </select>
            </div>
            <div class="field full-span">
                <label>${t("paymentDate")}</label>
                <input name="payment_date" type="date" value="${today()}">
            </div>
            <div class="field full-span">
                <label>${t("notes")}</label>
                <input name="notes" placeholder="e.g. Installment 1, Receipt #104">
            </div>
            <div class="form-actions full-span">
                <button class="button button-primary" type="submit">${t("save")}</button>
            </div>
        </form>
    `);

    $("#addPaymentForm").onsubmit = async (e) => {
        e.preventDefault();
        const data = Object.fromEntries(new FormData(e.target));
        data.amount = parseFloat(data.amount);
        try {
            if (window.AERODENT_ONLINE) {
                await window.AERODENT_API.post(`/api/invoices/${invoiceId}/payments`, data);
                $("#modal")?.classList.remove("show");
                toast(t("paymentRecorded"));
                await loadOnlineInvoices();
            } else {
                inv.paidAmount = (inv.paidAmount || 0) + data.amount;
                inv.balance = Math.max(0, (inv.amount || 0) - (inv.discount || 0) - inv.paidAmount);
                if (inv.balance <= 0) inv.status = "paid";
                else inv.status = "partially-paid";
                await dbPut("invoices", inv);
                $("#modal")?.classList.remove("show");
                toast(t("paymentRecorded"));
                await refresh();
            }
        } catch (err) {
            toast(err.message || "Failed to record payment");
        }
    };
}

function printInvoices() {
    document.body.classList.add("printing-invoice");
    setTimeout(() => {
        printPage(t("invoice")).then(() => {
            setTimeout(() => {
                document.body.classList.remove("printing-invoice");
            }, 500);
        });
    }, 50);
}


