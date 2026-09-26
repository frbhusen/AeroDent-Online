function bindPatientEvents() {
    $$(`[data-patient-page]`).forEach((button) => {
        button.onclick = async () => {
            const direction = button.dataset.patientPage;
            if (direction === "previous" && state.patientPage > 1) state.patientPage -= 1;
            if (direction === "next" && state.patientPage < state.patientPages) state.patientPage += 1;
            await refreshOnlinePatients();
        };
    });

    $$("[data-patient-id]").forEach(
        (row) => {
            row.onclick = async () => {
                const patientId = Number(row.dataset.patientId);
                let targetPatient = state.patients.find(
                    (patient) => patient.id === patientId
                ) || null;

                if (!targetPatient && state.dashboard?.recent_patients) {
                    targetPatient = state.dashboard.recent_patients.find((p) => p.id === patientId) || null;
                }
                if (!targetPatient && window.AERODENT_ONLINE) {
                    try {
                        const res = await window.AERODENT_API.get(`/api/patients/${patientId}`);
                        if (res.data) targetPatient = res.data;
                    } catch (err) {
                        console.error("Failed to load patient:", err);
                    }
                }

                state.selectedPatient = targetPatient;

                if (state.view === "dashboard" && targetPatient) {
                    state.view = "patients";
                }

                render();
                if (window.AERODENT_ONLINE && targetPatient) {
                    if (state.view === "odontogram") await loadOnlineOdontogram();
                    else if (state.view === "treatments") {
                        state.treatmentPage = 1;
                        state.invoicePage = 1;
                        await loadOnlineTreatments();
                        await loadOnlineInvoices();
                    } else if (state.view === "treatmentPlan") {
                        state.treatmentPlanPage = 1;
                        await loadOnlineTreatmentPlans();
                    } else if (state.view === "prescriptions") {
                        state.prescriptionPage = 1;
                        await loadOnlinePrescriptions();
                    } else if (state.view === "xrays") {
                        state.xrayPage = 1;
                        await loadOnlineXrays();
                    }
                    render();
                }
            };
        }
    );

    const patientRecordSelect =
        $("#patientRecordSelect");

    if (patientRecordSelect) {
        patientRecordSelect.onchange = async () => {
            const targetPatient = state.patients.find(
                (patient) => patient.id === Number(patientRecordSelect.value)
            ) || null;
            state.selectedPatient = targetPatient;

            render();
            if (window.AERODENT_ONLINE && targetPatient) {
                if (state.view === "odontogram") await loadOnlineOdontogram();
                else if (state.view === "treatments") {
                    state.treatmentPage = 1;
                    state.invoicePage = 1;
                    await loadOnlineTreatments();
                    await loadOnlineInvoices();
                } else if (state.view === "treatmentPlan") {
                    state.treatmentPlanPage = 1;
                    await loadOnlineTreatmentPlans();
                } else if (state.view === "prescriptions") {
                    state.prescriptionPage = 1;
                    await loadOnlinePrescriptions();
                } else if (state.view === "xrays") {
                    state.xrayPage = 1;
                    await loadOnlineXrays();
                }
            }
        };
    }

    const odontogramPatientSelect =
        $("#odontogramPatientSelect");

    if (odontogramPatientSelect) {
        odontogramPatientSelect.onchange = () => {
            state.selectedPatient =
                state.patients.find(
                    (patient) =>
                        patient.id ===
                        Number(
                            odontogramPatientSelect.value
                        )
                ) || null;

            render();
            if (window.AERODENT_ONLINE) loadOnlineOdontogram();
        };
    }

        const treatmentPatientSelect =
        $("#treatmentPatientSelect");

    if (treatmentPatientSelect) {
        treatmentPatientSelect.onchange = async () => {
            const patientId = Number(treatmentPatientSelect.value) || null;

            // Use state.selectedPatient as single source of truth for patient context
            state.selectedPatient =
                state.patients.find(
                    (patient) =>
                        patient.id === patientId
                ) || null;

            if (window.AERODENT_ONLINE) {
                state.treatmentPage = 1;
                state.treatmentError = "";
                state.invoicePage = 1;
                state.invoiceError = "";
                await loadOnlineTreatments();
                await loadOnlineInvoices();
            }

            render();
        };
    }

    const treatmentPlanPatientSelect =
        $("#treatmentPlanPatientSelect");

    if (treatmentPlanPatientSelect) {
        treatmentPlanPatientSelect.onchange = async () => {
            const patientId =
                Number(
                    treatmentPlanPatientSelect.value
                ) || null;

            state.treatmentPlanPatientId =
                patientId;

            state.selectedPatient =
                state.patients.find(
                    (patient) =>
                        patient.id === patientId
                ) || null;

            if (window.AERODENT_ONLINE && state.selectedPatient) {
                state.treatmentPlanPage = 1;
                state.treatmentPlanError = "";
                await loadOnlineTreatmentPlans();
            }

            render();
        };
    }

    const prescriptionPatientSelect =
        $("#prescriptionPatientSelect");

    if (prescriptionPatientSelect) {
        prescriptionPatientSelect.onchange = async () => {
            state.prescriptionPatientId =
                Number(
                    prescriptionPatientSelect.value
                ) || null;

            state.selectedPatient =
                state.patients.find(
                    (patient) =>
                        patient.id ===
                        state.prescriptionPatientId
                ) || state.selectedPatient;

            if (window.AERODENT_ONLINE) {
                await loadOnlinePrescriptions();
            }

            render();
        };
    }

    const xrayPatientSelect =
        $("#xrayPatientSelect");

    if (xrayPatientSelect) {
        xrayPatientSelect.onchange = async () => {
            state.selectedPatient =
                state.patients.find(
                    (patient) =>
                        patient.id ===
                        Number(
                            xrayPatientSelect.value
                        )
                ) || null;

            if (window.AERODENT_ONLINE) {
                await loadOnlineXrays();
            }

            render();
        };
    }

    $$("[data-delete-patient]").forEach(
        (button) => {
            button.onclick = async () => {
                if (window.AERODENT_DEMO) {
                    toast(t("deleteDemoPatient"));
                    return;
                }
                if (
                    !confirm(
                        t("confirmDeletePatient")
                    )
                ) {
                    return;
                }

                const patientId =
                    Number(
                        button.dataset
                            .deletePatient
                    );

                try {
                    if (window.AERODENT_ONLINE) {
                        if (state.patientSaving) return;
                        state.patientSaving = true;
                        button.disabled = true;
                        const response = await window.AERODENT_API.delete(`/api/patients/${patientId}`);
                        if (response !== null) {
                            // The API uses 204; this branch remains intentionally empty.
                        }
                        if (state.selectedPatient?.id === patientId) state.selectedPatient = null;
                        await refreshOnlinePatients(true);
                        return;
                    }

                    const backup =
                        await getPatientBackup(
                            patientId
                        );

                    await dbDeletePatient(
                        patientId
                    );

                    if (
                        state.selectedPatient
                            ?.id === patientId
                    ) {
                        state.selectedPatient =
                            null;
                    }

                    state.treatmentPatientId =
                        null;

                    state.prescriptionPatientId =
                        null;

                    await refresh(true);

                    showUndo(
                        t("patientDeleted"),
                        async () => {
                            await restorePatientBackup(
                                backup
                            );

                            state.selectedPatient =
                                backup.patient;

                            state.treatmentPatientId =
                                backup.patient.id;

                            state.treatmentPlanPatientId =
                                backup.patient.id;

                            state.prescriptionPatientId =
                                backup.patient.id;

                            await refresh();
                        }
                    );

                } catch (error) {
                    console.error(
                        "Patient deletion failed:",
                        error
                    );

                    toast(
                        error.message || "Unable to delete patient."
                    );
                } finally {
                    state.patientSaving = false;
                }
            };
        }
    );
}


function bindTreatmentPlanEvents() {
    $$("[data-treatment-plan-page]").forEach((button) => {
        button.onclick = async () => {
            const direction = button.dataset.treatmentPlanPage;
            if (direction === "previous" && state.treatmentPlanPage > 1) state.treatmentPlanPage -= 1;
            if (direction === "next" && state.treatmentPlanPage < state.treatmentPlanPages) state.treatmentPlanPage += 1;
            await loadOnlineTreatmentPlans();
        };
    });

    $$("[data-delete-treatment-plan]").forEach((button) => {
        button.onclick = () => {
            const planId = Number(button.dataset.deleteTreatmentPlan);
            deleteTreatmentPlan(planId);
        };
    });

    $$("[data-edit-treatment-plan]").forEach((button) => {
        button.onclick = () => {
            const planId = Number(button.dataset.editTreatmentPlan);
            editTreatmentPlan(planId);
        };
    });
}


function bindTreatmentEvents() {
    $$("[data-print-invoices]").forEach((button) => {
        button.onclick = () => printInvoices();
    });

    $$("[data-treatment-status]").forEach((select) => {
        select.onchange = async () => {
            const treatmentId = Number(select.dataset.treatmentStatus);
            const treatment = state.treatments.find((item) => item.id === treatmentId);
            if (!treatment) return;

            const newStatus = select.value;
            const previousStatus = treatment.status;

            if (window.AERODENT_ONLINE) {
                try {
                    setTreatmentSaving(true);
                    const response = await window.AERODENT_API.patch(`/api/treatments/${treatmentId}`, { status: newStatus });
                    const index = state.treatments.findIndex((item) => item.id === treatmentId);
                    if (index !== -1 && selectedTreatmentPatient()?.id === treatment.patientId) {
                        state.treatments[index] = mapApiTreatment(response.data);
                    }
                    toast(t("saved"));
                    render();
                } catch (error) {
                    select.value = previousStatus;
                    state.treatmentError = treatmentErrorMessage(error);
                    state.treatmentReadOnly = error.status === 403;
                    toast(state.treatmentError);
                    render();
                } finally {
                    setTreatmentSaving(false);
                }
            } else {
                try {
                    await dbPut("treatments", { ...treatment, status: newStatus });
                    toast(t("saved"));
                    await refresh();
                } catch (error) {
                    console.error("Failed to update treatment status:", error);
                    select.value = previousStatus;
                    toast("Unable to update status.");
                    render();
                }
            }
        };
    });

    $$("[data-treatment-page]").forEach((button) => {
        button.onclick = async () => {
            const direction = button.dataset.treatmentPage;
            if (direction === "previous" && state.treatmentPage > 1) state.treatmentPage -= 1;
            if (direction === "next" && state.treatmentPage < state.treatmentPages) state.treatmentPage += 1;
            await loadOnlineTreatments();
        };
    });

    $$("[data-edit-treatment]").forEach((button) => {
        button.onclick = () => editTreatment(Number(button.dataset.editTreatment));
    });

    $$("[data-delete-treatment]").forEach((button) => {
        button.onclick = () => deleteTreatment(Number(button.dataset.deleteTreatment));
    });

    $$("[data-invoice-page]").forEach((button) => {
        button.onclick = async () => {
            const direction = button.dataset.invoicePage;
            if (direction === "previous" && state.invoicePage > 1) state.invoicePage -= 1;
            if (direction === "next" && state.invoicePage < state.invoicePages) state.invoicePage += 1;
            await loadOnlineInvoices();
        };
    });

    $$("[data-add-payment]").forEach((button) => {
        button.onclick = () => openAddPaymentModal(Number(button.dataset.addPayment));
    });

    $$("[data-edit-invoice]").forEach((button) => {
        button.onclick = () => editInvoice(Number(button.dataset.editInvoice));
    });

    $$("[data-delete-invoice]").forEach((button) => {
        button.onclick = () => deleteInvoice(Number(button.dataset.deleteInvoice));
    });
}


function bindAppointmentEvents() {
    // Clicks on inline controls inside an agenda card must not also open the card.
    $$("[data-stop-propagation]").forEach((node) => {
        node.onclick = (event) => event.stopPropagation();
    });

    $$("[data-update-appt-status]").forEach((select) => {
        select.onchange = async (e) => {
            const apptId = Number(select.dataset.updateApptStatus);
            const newStatus = e.target.value;
            const targetAppt = state.appointments.find((a) => a.id === apptId);
            try {
                if (window.AERODENT_ONLINE) {
                    await window.AERODENT_API.patch(`/api/appointments/${apptId}`, { status: newStatus });
                    toast(`Status: ${t(newStatus) || newStatus}`);
                    await loadOnlineAppointments();
                } else {
                    if (targetAppt) {
                        targetAppt.status = newStatus;
                        await dbPut("appointments", targetAppt);
                        render();
                    }
                }
                if (newStatus === "cancelled" && targetAppt && typeof promptWaitlistAutoFill === "function") {
                    promptWaitlistAutoFill(targetAppt);
                }
            } catch (err) {
                toast(err.message || "Failed to update appointment status");
            }
        };
    });

    $$("[data-delete-appointment]").forEach((button) => {
        button.onclick = () => {
            const appointmentId = Number(button.dataset.deleteAppointment);
            deleteAppointment(appointmentId);
        };
    });

    $$("[data-edit-appointment]").forEach((button) => {
        button.onclick = () => editAppointment(Number(button.dataset.editAppointment));
    });

    const toggleWaitlistBtn = $("#toggleWaitlistBtn");
    if (toggleWaitlistBtn) {
        toggleWaitlistBtn.onclick = () => {
            state.showWaitlistPanel = !state.showWaitlistPanel;
            render();
        };
    }

    $$("[data-action='addWaitlist']").forEach((btn) => {
        btn.onclick = () => {
            if (typeof addWaitlistEntry === "function") addWaitlistEntry();
        };
    });

    $$("[data-book-waitlist]").forEach((btn) => {
        btn.onclick = async () => {
            const waitlistId = Number(btn.dataset.bookWaitlist);
            const w = (state.waitlist || []).find((x) => x.id === waitlistId);
            const targetDate = w?.preferred_date ? w.preferred_date : state.agendaDate;
            const targetTime = w?.preferred_time && /^\d{2}:\d{2}$/.test(w.preferred_time) ? w.preferred_time : "10:00";
            if (typeof bookWaitlistIntoSlot === "function") {
                await bookWaitlistIntoSlot(waitlistId, targetDate, targetTime);
            }
        };
    });

    $$("[data-delete-waitlist]").forEach((btn) => {
        btn.onclick = async () => {
            const waitlistId = Number(btn.dataset.deleteWaitlist);
            if (typeof deleteWaitlistEntry === "function") {
                await deleteWaitlistEntry(waitlistId);
            }
        };
    });

    // Draggable appointments
    $$(".appointment[draggable=true]").forEach((el) => {
        el.ondragstart = (e) => {
            const apptId = Number(el.dataset.appointmentId);
            e.dataTransfer.setData("application/json", JSON.stringify({ type: "appointment", id: apptId }));
            e.dataTransfer.effectAllowed = "move";
            el.classList.add("is-dragging");
        };
        el.ondragend = () => {
            el.classList.remove("is-dragging");
            $$(".is-slot-dragover").forEach((s) => s.classList.remove("is-slot-dragover"));
            $$(".is-day-dragover").forEach((d) => d.classList.remove("is-day-dragover"));
        };
    });

    // Draggable waitlist cards
    $$(".waitlist-card[draggable=true]").forEach((el) => {
        el.ondragstart = (e) => {
            const waitlistId = Number(el.dataset.waitlistId);
            e.dataTransfer.setData("application/json", JSON.stringify({ type: "waitlist", id: waitlistId }));
            e.dataTransfer.effectAllowed = "copyMove";
            el.classList.add("is-dragging");
        };
        el.ondragend = () => {
            el.classList.remove("is-dragging");
            $$(".is-slot-dragover").forEach((s) => s.classList.remove("is-slot-dragover"));
            $$(".is-day-dragover").forEach((d) => d.classList.remove("is-day-dragover"));
        };
    });

    // Time slot drop targets
    $$(".agenda-slot-target").forEach((slot) => {
        slot.ondragover = (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = "move";
            slot.classList.add("is-slot-dragover");
        };
        slot.ondragleave = (e) => {
            if (!slot.contains(e.relatedTarget)) {
                slot.classList.remove("is-slot-dragover");
            }
        };
        slot.ondrop = async (e) => {
            e.preventDefault();
            slot.classList.remove("is-slot-dragover");
            try {
                const raw = e.dataTransfer.getData("application/json") || e.dataTransfer.getData("text/plain");
                if (!raw) return;
                const data = JSON.parse(raw);
                const slotTime = slot.dataset.slotTime;
                if (!slotTime) return;

                if (data.type === "appointment" && typeof rescheduleAppointment === "function") {
                    await rescheduleAppointment(data.id, state.agendaDate, slotTime);
                } else if (data.type === "waitlist" && typeof bookWaitlistIntoSlot === "function") {
                    await bookWaitlistIntoSlot(data.id, state.agendaDate, slotTime);
                }
            } catch (err) {
                console.error("Drop error:", err);
            }
        };
    });

    // Calendar week day drop targets
    $$(".calendar-day[data-day-target]").forEach((dayBtn) => {
        dayBtn.ondragover = (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = "move";
            dayBtn.classList.add("is-day-dragover");
        };
        dayBtn.ondragleave = (e) => {
            if (!dayBtn.contains(e.relatedTarget)) {
                dayBtn.classList.remove("is-day-dragover");
            }
        };
        dayBtn.ondrop = async (e) => {
            e.preventDefault();
            dayBtn.classList.remove("is-day-dragover");
            try {
                const raw = e.dataTransfer.getData("application/json") || e.dataTransfer.getData("text/plain");
                if (!raw) return;
                const data = JSON.parse(raw);
                const targetDate = dayBtn.dataset.dayTarget;
                if (!targetDate) return;

                if (data.type === "appointment" && typeof rescheduleAppointment === "function") {
                    const appt = state.appointments.find((a) => a.id === data.id);
                    await rescheduleAppointment(data.id, targetDate, appt ? appt.startTime : "10:00");
                } else if (data.type === "waitlist" && typeof bookWaitlistIntoSlot === "function") {
                    await bookWaitlistIntoSlot(data.id, targetDate, "10:00");
                }
            } catch (err) {
                console.error("Day drop error:", err);
            }
        };
    });

    $$("[data-agenda-date]").forEach((button) => {
        button.onclick = async () => {
            const current = new Date(`${state.agendaDate}T12:00:00`);
            const prevAgendaDate = state.agendaDate;

            if (button.dataset.agendaDate === "previous") {
                current.setDate(current.getDate() - 1);
            } else if (button.dataset.agendaDate === "next") {
                current.setDate(current.getDate() + 1);
            }

            state.agendaDate = ["previous", "next"].includes(button.dataset.agendaDate)
                ? current.toISOString().slice(0, 10)
                : button.dataset.agendaDate === "today"
                    ? today()
                    : button.dataset.agendaDate;

            if (window.AERODENT_ONLINE) {
                // If week changed, fetch new week
                const prevWeekDates = calendarWeekDates(prevAgendaDate);
                const newWeekDates = calendarWeekDates(state.agendaDate);
                if (prevWeekDates[0] !== newWeekDates[0]) {
                    await loadOnlineAppointments();
                } else {
                    render();
                }
            } else {
                render();
            }
        };
    });
}


function bindXrayEvents() {
    $$("[data-open-xray]").forEach((element) => {
        element.onclick = () => {
            const xrayId = Number(element.dataset.openXray);
            openXrayViewer(xrayId);
        };
    });

    $$("[data-delete-xray]").forEach((button) => {
        button.onclick = async (event) => {
            event.stopPropagation();
            const xrayId = Number(button.dataset.deleteXray);
            await deleteXrayRecord(xrayId);
        };
    });

    const xray = $("#xrayUpload");
    if (xray) {
        xray.onchange = async () => {
            const file = xray.files[0];
            xray.value = "";
            await handleXrayUploadFile(file);
        };
    }
}


function bindPrescriptionEvents() {
    $$(
        "[data-edit-prescription]"
    ).forEach(
        (button) => {
            button.onclick = () =>
                editPrescription(
                    Number(
                        button.dataset
                            .editPrescription
                    )
                );
        }
    );
    $$("[data-delete-prescription]").forEach((button) => {
        button.onclick = () => deletePrescription(Number(button.dataset.deletePrescription));
    });
    $$(
        "[data-print-prescription]"
    ).forEach(
        (button) => {
            button.onclick = () =>
                printPrescription(
                    Number(
                        button.dataset
                            .printPrescription
                    )
                );
        }
    );
    $$(".quick-med-chip").forEach((chip) => {
        chip.onclick = () => {
            const med = {
                name: chip.dataset.quickMed || "",
                dosage: chip.dataset.dosage || "",
                frequency: chip.dataset.frequency || "",
                duration: chip.dataset.duration || "",
                instructions: chip.dataset.instructions || "",
            };
            const modalForm = $("#rxForm");
            if (modalForm && $("#prescriptionMedications")) {
                const container = $("#prescriptionMedications");
                const index = container.querySelectorAll(".prescription-edit-medication").length;
                container.insertAdjacentHTML("beforeend", prescriptionMedicationFields(med, index));
                bindPrescriptionMedicationControls();
                toast(`${med.name} ${t("added") || "added"}`);
            } else {
                addPrescription(med);
            }
        };
    });
}


function bindFormEvents() {
    const form =
        $("#patientForm");

    if (form) {
        form.onsubmit =
            async (event) => {
                event.preventDefault();

                const data =
                    Object.fromEntries(
                        new FormData(
                            form
                        )
                    );

                const updatedPatient = {
                    ...state.selectedPatient,
                    ...data,
                };

                if (window.AERODENT_ONLINE) {
                    if (state.patientSaving) return;
                    state.patientSaving = true;
                    const submitButton = form.querySelector("button[type=submit], button:not([type=button])");
                    if (submitButton) submitButton.disabled = true;
                    try {
                        const response = await window.AERODENT_API.patch(
                            `/api/patients/${state.selectedPatient.id}`,
                            patientApiPayload(updatedPatient),
                        );
                        state.selectedPatient = mapApiPatient(response.data);
                        toast(t("patientSaved"));
                        await refreshOnlinePatients();
                    } catch (error) {
                        toast(error.message);
                    } finally {
                        state.patientSaving = false;
                        if (submitButton) submitButton.disabled = false;
                    }
                    return;
                }

                await dbPut(
                    "patients",
                    updatedPatient
                );

                const patientAppointments =
                    state.appointments.filter(
                        (appointment) =>
                            appointment.patientId ===
                            updatedPatient.id
                    );

                for (const appointment of patientAppointments) {
                    await dbPut(
                        "appointments",
                        {
                            ...appointment,
                            patientName:
                                updatedPatient.name,
                        }
                    );
                }

                toast(
                    t("patientSaved")
                );

                await refresh();
            };
    }

    const settingsForm =
        $("#settingsForm");

    if (settingsForm) {
        settingsForm.onsubmit =
            async (event) => {

                event.preventDefault();

                await dbPut(
                    "settings",
                    {
                        ...state.settings,

                        id: 1,

                        ...Object.fromEntries(
                            new FormData(
                                settingsForm
                            )
                        ),
                    }
                );

                toast(
                    t("saved")
                );

                await refresh();
            };
    }

    const onlineSettingsForm = $("#onlineSettingsForm");
    if (onlineSettingsForm) {
        onlineSettingsForm.onsubmit = async (event) => {
            event.preventDefault();
            const data = Object.fromEntries(new FormData(onlineSettingsForm));
            try {
                await window.AERODENT_API.patch("/api/settings", {
                    name: data.name,
                    phone: data.phone || "",
                    address: data.address || "",
                    currency: data.currency || "SYR",
                    slot_duration: Number(data.slot_duration) || 30,
                    work_start: data.work_start || "09:00",
                    work_end: data.work_end || "18:00",
                    inventory_expiry_warning_days: Number(data.inventory_expiry_warning_days) || 60,
                });
                toast(t("savedOnline"));
                await loadOnlineSettings();
                render();
            } catch (error) {
                toast(error.message || "Failed to update clinic settings");
            }
        };
    }

    const changePasswordForm = $("#changePasswordForm");
    if (changePasswordForm) {
        changePasswordForm.onsubmit = async (event) => {
            event.preventDefault();
            const data = Object.fromEntries(new FormData(changePasswordForm));
            if (data.new_password !== data.confirm_password) {
                toast(t("passwordMismatch") || "New passwords do not match.");
                return;
            }
            try {
                const res = await window.AERODENT_API.post("/api/auth/change-password", {
                    current_password: data.current_password,
                    new_password: data.new_password,
                });
                toast(t("passwordChangedSuccess") || "Password updated successfully.");
                changePasswordForm.reset();
            } catch (err) {
                toast(err.message || "Failed to change password.");
            }
        };
    }

    $$("[data-toggle-staff-active]").forEach((button) => {
        button.onclick = () => {
            const userId = Number(button.dataset.toggleStaffActive);
            const currentActive = button.dataset.active === "true";
            toggleStaffActive(userId, currentActive);
        };
    });

    $$("[data-edit-staff]").forEach((button) => {
        button.onclick = () => {
            const userId = Number(button.dataset.editStaff);
            editStaff(userId);
        };
    });

    $$("[data-delete-staff]").forEach((button) => {
        button.onclick = () => {
            const userId = Number(button.dataset.deleteStaff);
            deleteStaff(userId);
        };
    });

    const saveToothNote =
        $("#saveToothNote");

    if (saveToothNote) {
        saveToothNote.onclick =
            saveCurrentToothNote;
    }
}


function bindNavigationEvents() {
    $$("[data-view]").forEach(
        (element) => {
            element.onclick = () => navigateTo(element.dataset.view);
        }
    );

    $$("[data-tooth]").forEach(
        (element) => {
            element.onclick = () =>
                openTooth(
                    Number(
                        element.dataset
                            .tooth
                    )
                );
        }
    );

    $$("[data-mode]").forEach(
        (element) => {
            element.onclick = () => {
                state.toothMode =
                    element.dataset.mode;

                render();
            };
        }
    );

    $$("[data-action]").forEach(
        (element) => {
            element.onclick = () =>
                actions(
                    element.dataset.action
                );
        }
    );
}


function bindView() {
    bindPatientEvents();
    bindTreatmentPlanEvents();
    bindTreatmentEvents();
    bindAppointmentEvents();
    bindXrayEvents();
    bindPrescriptionEvents();
    bindFormEvents();
    bindNavigationEvents();
    bindAdminEvents();
    bindHREvents();
    if (typeof bindOutreachEvents === "function") bindOutreachEvents();
    if (typeof bindActiveSessionEvents === "function") bindActiveSessionEvents();

    const refreshAuditBtn = $("#refreshAuditBtn");
    if (refreshAuditBtn) {
        refreshAuditBtn.onclick = async () => {
            if (typeof loadAuditLogs === "function") await loadAuditLogs();
            render();
        };
    }
    if (typeof bindAuditLogEvents === "function") {
        bindAuditLogEvents();
    }
    if (typeof bindInventoryEvents === "function") {
        bindInventoryEvents();
    }

    const searchInput = $("#globalSearch");
    if (searchInput) {
        searchInput.onclick = (e) => {
            e.preventDefault();
            if (typeof openCommandPalette === "function") openCommandPalette();
        };
        searchInput.onfocus = (e) => {
            e.preventDefault();
            if (typeof openCommandPalette === "function") openCommandPalette();
            searchInput.blur();
        };
    }
}

// ─────────────────────────────────────────────────────────────
//  HR Events
// ─────────────────────────────────────────────────────────────
function bindHREvents() {
    if (state.view !== "hr") return;

    // Tab switching (also used by alert banner link)
    $$("[data-hr-tab]").forEach(btn => {
        btn.onclick = async () => {
            _stopHRTimer();
            state.hrTab = btn.dataset.hrTab;
            render();
        };
    });

    // Punch In / Punch Out
    const punchBtn = $("#hrPunchBtn");
    if (punchBtn) {
        punchBtn.onclick = async () => {
            const action = punchBtn.dataset.action;
            const notes = ($("#hrPunchNotes")?.value || "").trim();
            try {
                await window.AERODENT_API.post("/api/hr/time-clock/punch", {
                    action,
                    notes: notes || undefined,
                });
                await loadOnlineHRData();
                render();
            } catch (err) {
                toast(err?.message || t("errorOccurred"));
            }
        };
    }

    // Shift filter
    const filterBtn = $("#hrShiftFilterBtn");
    if (filterBtn) {
        filterBtn.onclick = async () => {
            const from = $("#hrShiftFrom")?.value;
            const to   = $("#hrShiftTo")?.value;
            try {
                const params = new URLSearchParams();
                if (from) params.set("start_date", from);
                if (to)   params.set("end_date", to);
                const res = await window.AERODENT_API.get(`/api/hr/shifts?${params}`);
                state.hrShifts = res?.data || [];
                render();
            } catch (err) {
                toast(err?.message || t("errorOccurred"));
            }
        };
    }

    // Add shift button
    const addShiftBtn = $("#hrAddShiftBtn");
    if (addShiftBtn) {
        addShiftBtn.onclick = () => {
            modal("", _hrShiftModal(null));
            _bindShiftForm(null);
        };
    }

    // Edit shift
    $$("[data-hr-edit-shift]").forEach(btn => {
        btn.onclick = () => {
            const id = Number(btn.dataset.hrEditShift);
            const shift = state.hrShifts.find(s => s.id === id);
            if (!shift) return;
            modal("", _hrShiftModal(shift));
            _bindShiftForm(shift);
        };
    });

    // Delete shift
    $$("[data-hr-delete-shift]").forEach(btn => {
        btn.onclick = async () => {
            const id = Number(btn.dataset.hrDeleteShift);
            if (!confirm(t("confirmDelete"))) return;
            try {
                await window.AERODENT_API.delete(`/api/hr/shifts/${id}`);
                await loadOnlineHRData();
                render();
            } catch (err) {
                toast(err?.message || t("errorOccurred"));
            }
        };
    });

    // Add credential button
    const addCredBtn = $("#hrAddCredBtn");
    if (addCredBtn) {
        addCredBtn.onclick = () => {
            modal("", _hrCredentialModal(null));
            _bindCredForm(null);
        };
    }

    // Edit credential
    $$("[data-hr-edit-cred]").forEach(btn => {
        btn.onclick = () => {
            const id = Number(btn.dataset.hrEditCred);
            const cred = state.hrCredentials.find(c => c.id === id);
            if (!cred) return;
            modal("", _hrCredentialModal(cred));
            _bindCredForm(cred);
        };
    });

    // Delete credential
    $$("[data-hr-delete-cred]").forEach(btn => {
        btn.onclick = async () => {
            const id = Number(btn.dataset.hrDeleteCred);
            if (!confirm(t("confirmDelete"))) return;
            try {
                await window.AERODENT_API.delete(`/api/hr/credentials/${id}`);
                await loadOnlineHRData();
                render();
            } catch (err) {
                toast(err?.message || t("errorOccurred"));
            }
        };
    });
}

function _bindShiftForm(existingShift) {
    const form = $("#hrShiftForm");
    if (!form) return;
    const closeBtn = $("#modalCloseBtn");
    if (closeBtn) closeBtn.onclick = () => $("#modal").classList.remove("show");

    form.onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData(form);
        const payload = {
            user_id: Number(fd.get("user_id")),
            date: fd.get("date"),
            start_time: fd.get("start_time"),
            end_time: fd.get("end_time"),
            shift_type: fd.get("shift_type"),
            status: fd.get("status"),
            notes: fd.get("notes") || undefined,
        };
        try {
            const shiftId = fd.get("shift_id");
            if (shiftId) {
                await window.AERODENT_API.patch(`/api/hr/shifts/${shiftId}`, payload);
            } else {
                await window.AERODENT_API.post("/api/hr/shifts", payload);
            }
            $("#modal").classList.remove("show");
            await loadOnlineHRData();
            render();
        } catch (err) {
            toast(err?.message || t("errorOccurred"));
        }
    };
}

function _bindCredForm(existingCred) {
    const form = $("#hrCredForm");
    if (!form) return;
    const closeBtn = $("#modalCloseBtn");
    if (closeBtn) closeBtn.onclick = () => $("#modal").classList.remove("show");

    form.onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData(form);
        const payload = {
            user_id: Number(fd.get("user_id")),
            title: fd.get("title"),
            credential_type: fd.get("credential_type"),
            credential_number: fd.get("credential_number") || undefined,
            issuing_authority: fd.get("issuing_authority") || undefined,
            issue_date: fd.get("issue_date") || undefined,
            expiry_date: fd.get("expiry_date"),
            notes: fd.get("notes") || undefined,
        };
        try {
            const credId = fd.get("cred_id");
            if (credId) {
                await window.AERODENT_API.patch(`/api/hr/credentials/${credId}`, payload);
            } else {
                await window.AERODENT_API.post("/api/hr/credentials", payload);
            }
            $("#modal").classList.remove("show");
            await loadOnlineHRData();
            render();
        } catch (err) {
            toast(err?.message || t("errorOccurred"));
        }
    };
}


function bindAdminEvents() {
    if (state.auth?.user?.role !== "super_admin") return;

    $$("[data-admin-extend-clinic]").forEach((btn) => {
        btn.onclick = async () => {
            const clinicId = Number(btn.dataset.adminExtendClinic);
            const days = Number(btn.dataset.days || 30);
            try {
                await window.AERODENT_API.patch(`/api/admin/clinics/${clinicId}`, {
                    extend_days: days,
                    subscription_status: "active",
                    is_active: true,
                });
                toast(t("subscriptionUpdated"));
                await loadAdminClinics();
                await loadAdminMetrics();
                render();
            } catch (err) {
                toast(err.message || "Failed to extend subscription");
            }
        };
    });

    $$("[data-admin-manage-clinic]").forEach((btn) => {
        btn.onclick = () => {
            adminOpenManageSubscriptionModal(Number(btn.dataset.adminManageClinic));
        };
    });

    $$("[data-admin-edit-clinic]").forEach((btn) => {
        btn.onclick = () => {
            adminOpenEditClinicModal(Number(btn.dataset.adminEditClinic));
        };
    });

    $$("[data-admin-toggle-clinic]").forEach((btn) => {
        btn.onclick = () => {
            adminToggleClinicActive(
                Number(btn.dataset.adminToggleClinic),
                btn.dataset.active === "true"
            );
        };
    });

    $$("[data-admin-toggle-user]").forEach((btn) => {
        btn.onclick = () => {
            adminToggleUserActive(
                Number(btn.dataset.adminToggleUser),
                btn.dataset.active === "true",
                btn.dataset.role
            );
        };
    });

    $$("[data-admin-edit-user]").forEach((btn) => {
        btn.onclick = () => {
            adminOpenEditUserModal(Number(btn.dataset.adminEditUser));
        };
    });

    $$("[data-admin-delete-user]").forEach((btn) => {
        btn.onclick = () => {
            adminDeleteUser(Number(btn.dataset.adminDeleteUser));
        };
    });

    $$("[data-admin-delete-clinic]").forEach((btn) => {
        btn.onclick = () => {
            adminDeleteClinic(Number(btn.dataset.adminDeleteClinic));
        };
    });

    $$(".admin-filter-chip").forEach((chip) => {
        chip.onclick = () => {
            const status = chip.dataset.filterStatus;
            state.adminStatusFilter = status;
            loadAdminClinics(state.adminSearch, state.adminStatusFilter).then(() => render());
        };
    });

    const clinicSearch = $("#adminClinicSearch");
    if (clinicSearch) {
        clinicSearch.oninput = (e) => {
            state.adminSearch = e.target.value.trim();
            loadAdminClinics(state.adminSearch, state.adminStatusFilter).then(() => render());
        };
    }

    const clinicFilter = $("#adminClinicStatusFilter");
    if (clinicFilter) {
        clinicFilter.onchange = (e) => {
            state.adminStatusFilter = e.target.value;
            loadAdminClinics(state.adminSearch, state.adminStatusFilter).then(() => render());
        };
    }

    const userSearch = $("#adminUserSearch");
    if (userSearch) {
        userSearch.oninput = (e) => {
            state.adminUserSearch = e.target.value.trim();
            loadAdminUsers(
                state.adminUserClinicFilter !== "all" ? state.adminUserClinicFilter : null,
                state.adminUserRoleFilter,
                state.adminUserSearch
            ).then(() => render());
        };
    }

    const userRoleFilter = $("#adminUserRoleFilter");
    if (userRoleFilter) {
        userRoleFilter.onchange = (e) => {
            state.adminUserRoleFilter = e.target.value;
            loadAdminUsers(
                state.adminUserClinicFilter !== "all" ? state.adminUserClinicFilter : null,
                state.adminUserRoleFilter,
                state.adminUserSearch
            ).then(() => render());
        };
    }

    const userClinicFilter = $("#adminUserClinicFilter");
    if (userClinicFilter) {
        userClinicFilter.onchange = (e) => {
            state.adminUserClinicFilter = e.target.value;
            loadAdminUsers(
                state.adminUserClinicFilter !== "all" ? state.adminUserClinicFilter : null,
                state.adminUserRoleFilter,
                state.adminUserSearch
            ).then(() => render());
        };
    }
}


function bindGlobalEvents() {
    $("#langBtn").onclick =
        async () => {

            currentLanguage =
                currentLanguage === "en"
                    ? "ar"
                    : "en";

            if (window.AERODENT_ONLINE) {
                // Never write online clinic settings into the offline IndexedDB store.
                storeLanguagePreference(currentLanguage);
            } else {
                await dbPut(
                    "settings",
                    {
                        ...state.settings,
                        id: 1,
                        currentLanguage,
                    }
                );
            }

            render();

            if (
                document.body.classList.contains(
                    "drawer-open"
                )
            ) {
                openTooth(
                    state.selectedTooth
                );
            }
        };

    $("#newPatientBtn").onclick =
        () => newPatient();

    $("#unlockBtn").onclick =
        verifyPIN;

    $("#savePINBtn").onclick =
        savePIN;

    $("#pinInput").addEventListener(
        "keydown",
        (event) => {
            if (
                event.key ===
                "Enter"
            ) {
                verifyPIN();
            }
        }
    );

    $("#confirmPINInput").addEventListener(
        "keydown",
        (event) => {
            if (
                event.key ===
                "Enter"
            ) {
                savePIN();
            }
        }
    );

    $("#backupBtn").onclick =
        () => exportData();

    $("#closeDrawer").onclick =
        () =>
            document.body
                .classList
                .remove(
                    "drawer-open"
                );

    $("#drawerBackdrop").onclick =
        () =>
            document.body
                .classList
                .remove(
                    "drawer-open"
                );

    $("#modalClose").onclick =
        () =>
            $("#modal")
                .classList
                .remove(
                    "show"
                );

    $("#globalSearch").oninput =
        (event) => {

            const term =
                event.target.value
                    .toLowerCase();

            if (window.AERODENT_ONLINE) {
                state.patientSearch = event.target.value;
                state.patientPage = 1;
                clearTimeout(window.aerodentPatientSearchTimer);
                window.aerodentPatientSearchTimer = setTimeout(
                    () => refreshOnlinePatients(true),
                    250,
                );
                state.view = "patients";
                return;
            }

            const patient =
                state.patients.find(
                    (item) =>
                        item.name
                            .toLowerCase()
                            .includes(
                                term
                            ) ||
                        item.phone
                            ?.toLowerCase()
                            .includes(
                                term
                            )
                );

            if (patient) {
                state.selectedPatient =
                    patient;

                state.view =
                    "patients";

                render();
            }
        };

    const importInput = $("#importInput");

    if (importInput) {
        importInput.onchange = async (event) => {
            const file = event.target.files?.[0];

            if (!file) {
                return;
            }

            try {
                const source = await file.text();

                const data =
                    parseExcelBackup(source);

                validateImportedData(data);

                const confirmed = confirm(
                    t("confirmWipe")
                );

                if (!confirmed) {
                    return;
                }

                await safeImport(data);

                toast(t("restored"));

                state.selectedPatient = null;
                state.treatmentPatientId = null;
                state.treatmentPlanPatientId = null;
                state.prescriptionPatientId = null;

                await refresh(true);

            } catch (error) {
                console.error(
                    "Backup import failed:",
                    error
                );

                alert(
                    error?.message ||
                    "Invalid backup file."
                );

            } finally {
                /*
                 * Allow the same file to be
                 * selected again.
                 */
                importInput.value = "";
            }
        };
    }

    if (
        localStorage.getItem(
            "aerodent-sidebar-collapsed"
        ) === "true"
    ) {
        document.body.classList.add(
            "sidebar-collapsed"
        );
    }

    $("#sidebarToggle").onclick =
        () => {

            const collapsed =
                document.body.classList.toggle(
                    "sidebar-collapsed"
                );

            localStorage.setItem(
                "aerodent-sidebar-collapsed",
                String(collapsed)
            );

            setText();
        };

    bindKeyboardEvents();
    bindInactivityEvents();
}


function bindKeyboardEvents() {
    document.addEventListener(
        "keydown",
        (event) => {

            if (
                event.target.matches(
                    "input, textarea, select"
                )
            ) {
                return;
            }

            if (
                event.key === "Escape"
            ) {
                $("#modal")
                    .classList
                    .remove(
                        "show"
                    );

                document.body.classList.remove(
                    "drawer-open"
                );
            }

            if (
                event.key.toLowerCase() === "n"
                ||
                event.key.toLowerCase() === "ى"
            ) {
                newPatient();
            }

            if (
                event.key.toLowerCase() === "a"
                ||
                event.key.toLowerCase() === "ش"
            ) {
                addAppointment();
            }

            if (
                event.key.toLowerCase() === "p"
                ||
                event.key.toLowerCase() === "ط"
            ) {
                state.view =
                    "patients";

                render();
            }

            if (
                event.key.toLowerCase() === "o"
                ||
                event.key.toLowerCase() === "غ"
            ) {
                state.view =
                    "odontogram";

                render();
                if (window.AERODENT_ONLINE) loadOnlineOdontogram();
            }

            if (
                event.ctrlKey &&
                event.key.toLowerCase() ===
                "k"
                ||
                event.metaKey &&
                event.key.toLowerCase() ===
                "ن"
            ) {
                event.preventDefault();

                $("#globalSearch")
                    .focus();
            }
        }
    );
}


function bindInactivityEvents() {
    const activityEvents = [
        "mousemove",
        "mousedown",
        "keydown",
        "touchstart",
        "scroll",
    ];

    activityEvents.forEach((eventName) => {
        document.addEventListener(
            eventName,
            () => {
                const appShell =
                    document.querySelector(".app-shell");

                if (
                    appShell &&
                    !appShell.classList.contains("app-locked")
                ) {
                    resetInactivityTimer();
                }
            },
            true
        );
    });
}

bindGlobalEvents();








