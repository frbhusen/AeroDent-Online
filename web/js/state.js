const state = {
    auth: {
        authenticated: false,
        loading: true,
        user: null,
    },
    // Patients
    patientPage: 1,
    patientPerPage: 25,
    patientTotal: 0,
    patientPages: 0,
    patientSearch: "",
    patientLoading: false,
    patientError: "",
    patientSaving: false,

    // Treatments
    treatmentPage: 1,
    treatmentPerPage: 25,
    treatmentTotal: 0,
    treatmentPages: 0,
    treatmentLoading: false,
    treatmentError: "",
    treatmentSaving: false,
    treatmentReadOnly: false,

    // Treatment Plans
    treatmentPlanPage: 1,
    treatmentPlanPerPage: 25,
    treatmentPlanTotal: 0,
    treatmentPlanPages: 0,
    treatmentPlanLoading: false,
    treatmentPlanError: "",
    treatmentPlanSaving: false,
    treatmentPlanReadOnly: false,

    // Appointments
    agendaDate: new Date().toISOString().slice(0, 10),
    appointmentLoading: false,
    appointmentError: "",
    appointmentSaving: false,
    waitlist: [],
    waitlistLoading: false,
    waitlistError: "",
    showWaitlistPanel: false,

    // Prescriptions
    prescriptionLoading: false,
    prescriptionError: "",
    prescriptionSaving: false,
    prescriptionReadOnly: false,
    printPrescriptionId: null,

    // X-rays
    xrayLoading: false,
    xrayError: "",
    xraySaving: false,
    xrayReadOnly: false,

    // Invoices
    invoicePage: 1,
    invoicePerPage: 25,
    invoiceTotal: 0,
    invoicePages: 0,
    invoiceLoading: false,
    invoiceError: "",
    invoiceSaving: false,

    // Odontogram
    selectedTooth: 14,
    toothMode: "permanent",
    odontogramLoading: false,
    odontogramError: "",
    odontogramSaving: false,
    odontogramReadOnly: false,

    // Dashboard
    dashboardData: null,
    dashboardLoading: false,
    dashboardError: "",

    // Timeline
    timelineData: null,
    timelineLoading: false,
    timelineError: "",

    // Settings & Staff
    settings: {},
    settingsLoading: false,
    settingsError: "",
    settingsSaving: false,
    staffList: [],
    staffLoading: false,
    staffError: "",
    staffSaving: false,
    doctorsList: [],

    // Super Admin & Audit State
    adminMetrics: null,
    adminClinics: [],
    adminUsers: [],
    adminLoading: false,
    adminError: "",
    adminSearch: "",
    adminStatusFilter: "all",
    adminUserSearch: "",
    adminUserRoleFilter: "all",
    adminUserClinicFilter: "all",
    auditLogs: [],
    auditLogsLoading: false,
    auditLogsTotal: 0,
    auditFilterCategory: "all",
    auditSearchQuery: "",

    // HR-lite
    hrTab: "time_clock",
    hrShifts: [],
    hrTimeClockStatus: { clocked_in: false, elapsed_seconds: 0, entry: null },
    hrTimeClockRecords: [],
    hrCredentials: [],
    hrCredentialsSummary: { total: 0, active: 0, expiring_soon: 0, expired: 0, needs_attention: 0 },
    hrLoading: false,
    hrError: "",

    // Active View & Patient Selection
    view: "dashboard",
    selectedPatient: null,

    // Data arrays
    patients: [],
    odontograms: [],
    appointments: [],
    treatments: [],
    treatmentPlans: [],
    invoices: [],
    prescriptions: [],
    xrays: [],
};

const NAV = [
    ["dashboard", "📊", "dashboard"],
    ["odontogram", "🦷", "odontogram"],
    ["patients", "👥", "patients"],
    ["treatments", "🩺", "treatments"],
    ["treatmentPlan", "📋", "treatmentPlan"],
    ["appointments", "📅", "appointments"],
    ["prescriptions", "💊", "prescriptions"],
    ["xrays", "🩻", "xrays"],
    ["hr", "👔", "hrManagement"],
    ["settings", "⚙️", "settings"],
];

const SUPER_ADMIN_NAV = [
    ["admin_overview", "📊", "adminOverview"],
    ["admin_clinics", "🏥", "adminClinics"],
    ["admin_users", "👥", "adminUsers"],
    ["audit_logs", "📜", "auditLogs"],
];

const PROCEDURES = [
    ["decay", "decay"],
    ["filling", "filling"],
    ["crown", "crown"],
    ["rct", "rct"],
    ["extract", "extract"],
    ["implant", "implant"],
    ["clear", "clear"],
];
