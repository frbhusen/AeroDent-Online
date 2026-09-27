// Patient outreach: recall list and one-tap WhatsApp reminders (online mode).
// See docs/PROPOSED_CHANGES.md. Nothing is sent automatically: the link opens WhatsApp with a
// pre-filled message that the staff member reviews and sends from their own account.

const RECALL_MONTH_OPTIONS = [3, 6, 9, 12, 18, 24];
const RECALL_LIST_SIZE = 8;

// wa.me needs the full international number. Numbers saved without a country code are not
// guessed; the button explains how to fix the number instead.
function whatsappNumber(phone) {
    const raw = String(phone || "").trim();
    if (!/^(\+|00)/.test(raw)) return null;
    const digits = raw.replace(/^00/, "").replace(/\D/g, "");
    return digits.length >= 8 && digits.length <= 15 ? digits : null;
}

function outreachClinicName() {
    const name = state.settings?.clinicName || "";
    const placeholder = !name || name === "------ Dental Clinic" || /^Clinic #\d+$/.test(name);
    return placeholder ? "" : name;
}

function fillMessage(key, values) {
    return t(key).replace(/\{(\w+)\}/g, (_, name) => values[name] ?? "");
}

// Gregorian calendar and Latin digits in both languages, so patients read dates the same way
// the clinic's agenda shows them.
function outreachDate(isoDate) {
    const parsed = new Date(`${String(isoDate).slice(0, 10)}T00:00:00`);
    if (Number.isNaN(parsed.getTime())) return String(isoDate || "");
    return parsed.toLocaleDateString(currentLanguage === "ar" ? "ar-u-ca-gregory-nu-latn" : "en-GB", {
        weekday: "long",
        day: "numeric",
        month: "long",
    });
}

function appointmentReminderMessage(appointment) {
    const clinic = outreachClinicName();
    return fillMessage(clinic ? "waReminderMessage" : "waReminderMessageNoClinic", {
        patient: appointment.patientName || appointment.patient_name || "",
        clinic,
        date: outreachDate(appointment.date),
        time: appointment.startTime || appointment.start_time || "",
    });
}

function recallMessage(patient) {
    const clinic = outreachClinicName();
    return fillMessage(clinic ? "waRecallMessage" : "waRecallMessageNoClinic", {
        patient: patient.name || "",
        clinic,
    });
}

function whatsappButton(phone, message) {
    const number = whatsappNumber(phone);
    if (!number) {
        const reason = phone ? t("waNeedsInternationalPhone") : t("waNoPhone");
        return `<button type="button" class="button button-ghost button-sm whatsapp-button" disabled title="${esc(reason)}" aria-label="${esc(`${t("waSend")}: ${reason}`)}">💬 ${t("waSend")}</button>`;
    }
    const href = `https://wa.me/${number}?text=${encodeURIComponent(message)}`;
    return `<a class="button button-ghost button-sm whatsapp-button" href="${esc(href)}" target="_blank" rel="noopener noreferrer" title="${esc(t("waSendReminder"))}" data-stop-propagation>💬 ${t("waSend")}</a>`;
}

function appointmentWhatsappButton(appointment) {
    if (!window.AERODENT_ONLINE || appointment.status === "cancelled" || appointment.status === "completed") return "";
    return whatsappButton(appointment.patientPhone ?? appointment.patient_phone, appointmentReminderMessage(appointment));
}

// ------------------------------------------------------------------ recall list

async function loadRecallList() {
    if (!window.AERODENT_ONLINE || !hasPermission("patients.read")) return;
    const months = state.recallMonths || 6;
    state.recallLoading = true;
    try {
        const response = await window.AERODENT_API.get(`/api/patients/recall?months=${months}&per_page=${RECALL_LIST_SIZE}`);
        state.recall = { items: response.data || [], total: response.meta?.total ?? 0, months };
        state.recallError = "";
    } catch (error) {
        state.recallError = error.message;
    } finally {
        state.recallLoading = false;
    }
}

function renderRecallCard() {
    if (!window.AERODENT_ONLINE || !hasPermission("patients.read")) return "";
    const months = state.recallMonths || 6;
    const recall = state.recall || { items: [], total: 0 };
    const options = RECALL_MONTH_OPTIONS.map(
        (value) => `<option value="${value}" ${value === months ? "selected" : ""}>${fillMessage("recallMonthsOption", { months: value })}</option>`,
    ).join("");

    let body;
    if (state.recallError) {
        body = `<p class="muted">${esc(state.recallError)}</p>`;
    } else if (!recall.items.length) {
        body = `<div class="dashboard-empty-state"><span class="empty-state-icon">✅</span><p class="muted">${state.recallLoading ? t("loading") : t("recallEmpty")}</p></div>`;
    } else {
        body = recall.items.map((patient) => `
            <div class="recall-row">
                <button type="button" class="recall-patient" data-patient-id="${patient.id}">
                    <b>${esc(patient.name)}</b>
                    <small class="muted">${fillMessage("recallLastVisit", { date: esc(outreachDate(patient.last_visit)), months: Math.floor(patient.days_since / 30) })}</small>
                </button>
                ${whatsappButton(patient.phone, recallMessage(patient))}
            </div>`).join("");
        if (recall.total > recall.items.length) {
            body += `<p class="muted recall-more">${fillMessage("recallMore", { count: recall.total - recall.items.length })}</p>`;
        }
    }

    return `
        <section class="card dashboard-card recall-card">
            <div class="card-heading">
                <div class="card-title-group">
                    <span class="card-heading-icon">🔔</span>
                    <h2>${t("recallTitle")}${recall.total ? ` <span class="badge badge-amber">${recall.total}</span>` : ""}</h2>
                </div>
                <label class="recall-interval">
                    <span class="sr-only">${t("recallInterval")}</span>
                    <select id="recallMonths" aria-label="${t("recallInterval")}">${options}</select>
                </label>
            </div>
            <p class="muted recall-hint">${t("recallHint")}</p>
            <div class="recall-list">${body}</div>
        </section>`;
}

function bindOutreachEvents() {
    const select = $("#recallMonths");
    if (select) {
        select.onchange = async () => {
            state.recallMonths = Number(select.value) || 6;
            await loadRecallList();
            render();
        };
    }
}
