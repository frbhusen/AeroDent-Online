async function exportData() {
    if (window.AERODENT_ONLINE) {
        await exportClinicBackup();
        return;
    }
    const data = await dbExport();

    const sheets = Object.entries(data)
        .map(([name, rows]) => {
            const columns = [
                ...new Set(
                    rows.flatMap((row) =>
                        Object.keys(row)
                    )
                ),
            ];

            const header = columns
                .map(
                    (column) =>
                        `<th>${excelText(column)}</th>`
                )
                .join("");

            const body = rows
                .map(
                    (row) =>
                        `<tr>${columns
                            .map(
                                (column) =>
                                    `<td>${excelText(
                                        typeof row[column] ===
                                            "object"
                                            ? JSON.stringify(
                                                row[column]
                                            )
                                            : row[column]
                                    )}</td>`
                            )
                            .join("")}</tr>`
                )
                .join("");

            return `
                <h2>${excelText(name)}</h2>
                <table>
                    <thead>
                        <tr>${header}</tr>
                    </thead>
                    <tbody>
                        ${body}
                    </tbody>
                </table>
            `;
        })
        .join("");

    const workbook = `
        <!doctype html><html><head><meta charset="utf-8"><meta name="aerodent-export" content="1"><style>
                body {
                    font-family: Arial;
                }

                h2 {
                    background: #0369a1;
                    color: #fff;
                    padding: 8px;
                }

                table {
                    border-collapse: collapse;
                    margin-bottom: 24px;
                }

                th,
                td {
                    border: 1px solid #cbd5e1;
                    padding: 6px;
                    text-align: left;
                }

                th {
                    background: #e0f2fe;
                }
            </style>
        </head>

        <body>
            <h1>AeroDent Export</h1>
            ${sheets}
        </body>
        </html>
    `;

    const blob = new Blob(
        [workbook],
        {
            type: "application/vnd.ms-excel",
        }
    );

    const link =
        document.createElement("a");

    link.href =
        URL.createObjectURL(blob);

    link.download =
        `aerodent-export-${new Date()
            .toISOString()
            .replace(/[:.]/g, "-")}.xls`;

    link.style.display = "none";

    document.body.append(link);

    link.click();

    setTimeout(() => {
        URL.revokeObjectURL(link.href);
        link.remove();
    }, 1000);

    toast(t("exported"));
}


function parseExcelBackup(source) {
    if (
        !source ||
        typeof source !== "string"
    ) {
        throw new Error(
            "Backup file is empty."
        );
    }

    const parser = new DOMParser();

    const document =
        parser.parseFromString(
            source,
            "text/html"
        );

    const marker =
        document.querySelector(
            'meta[name="aerodent-export"]'
        );

    if (!marker) {
        throw new Error(
            "This file is not a valid AeroDent backup."
        );
    }

    const data = {};

    const headings = [
        ...document.querySelectorAll("h2"),
    ];

    for (const heading of headings) {
        const store =
            heading.textContent.trim();

        if (!STORES.includes(store)) {
            continue;
        }

        const table =
            heading.nextElementSibling;

        if (
            !table ||
            table.tagName !== "TABLE"
        ) {
            data[store] = [];
            continue;
        }

        const headers = [
            ...table.querySelectorAll(
                "thead th"
            ),
        ].map(
            (cell) =>
                cell.textContent.trim()
        );

        const rows = [
            ...table.querySelectorAll(
                "tbody tr"
            ),
        ];

        data[store] = rows.map(
            (row) => {
                const cells = [
                    ...row.querySelectorAll(
                        "td"
                    ),
                ];

                const item = {};

                cells.forEach(
                    (cell, index) => {
                        const key =
                            headers[index];

                        if (!key) {
                            return;
                        }

                        let value =
                            cell.textContent.trim();

                        if (value === "") {
                            item[key] = "";
                            return;
                        }

                        const numericFields = [
                            "id",
                            "patientId",
                            "toothNumber",
                            "fee",
                            "duration",
                            "paidAmount",
                            "balance",
                            "discount",
                            "slotDuration",
                        ];

                        if (
                            numericFields.includes(
                                key
                            )
                        ) {
                            const number =
                                Number(value);

                            if (
                                !Number.isFinite(
                                    number
                                )
                            ) {
                                throw new Error(
                                    `Invalid number in ${store}.${key}`
                                );
                            }

                            item[key] =
                                number;

                            return;
                        }
                        const booleanFields = [
                            "pinEnabled",
                        ];
                        if (booleanFields.includes(key)) {
                            if (value === "true") {
                                item[key] = true;
                                return;
                            }

                            if (value === "false") {
                                item[key] = false;
                                return;
                            }

                            throw new Error(
                                `Invalid boolean in ${store}.${key}`
                            );
                        }
                        const jsonFields = [
                            "items",
                            "medications",
                        ];
                        if (
                            jsonFields.includes(
                                key
                            )
                        ) {
                            try {
                                item[key] =
                                    JSON.parse(
                                        value
                                    );
                            } catch {
                                throw new Error(
                                    `Invalid JSON in ${store}.${key}`
                                );
                            }

                            return;
                        }

                        item[key] = value;
                    }
                );

                return item;
            }
        );
    }

    for (const store of STORES) {
        if (
            !Array.isArray(
                data[store]
            )
        ) {
            data[store] = [];
        }
    }

    return data;
}


async function importBackup(file) {
    if (!file) {
        throw new Error(
            "No backup file selected."
        );
    }

    const source =
        await file.text();

    const data =
        parseExcelBackup(source);

    validateBackup(data);

    if (
        !confirm(
            t("confirmWipe")
        )
    ) {
        return false;
    }

    await safeImport(data);

    await refresh();

    toast(t("restored"));

    return true;
}

// ------------------------------------------------------------------ online clinic backup
// Head doctors only (the server enforces clinic_data.export / clinic_data.import).
// The backup is a ZIP with every clinic record, the staff list, the audit log and the X-ray
// images byte-for-byte; see docs/CLINIC_BACKUP.md.

function backupFilename(response) {
    const header = response.headers.get("Content-Disposition") || "";
    const match = /filename="?([^";]+)"?/i.exec(header);
    return match ? match[1] : `aerodent-clinic-${today()}.zip`;
}

async function exportClinicBackup() {
    if (!hasPermission("clinic_data.export")) return;
    if (NativeShell.available) {
        // The Android download manager streams the archive straight to Downloads/AeroDent.
        const link = document.createElement("a");
        link.href = "/api/clinic/export";
        link.download = "";
        document.body.append(link);
        link.click();
        link.remove();
        toast(t("backupExportStarted"));
        return;
    }
    toast(t("backupExportPreparing"));
    try {
        const response = await fetch("/api/clinic/export", { credentials: "include" });
        if (!response.ok) {
            const payload = await response.json().catch(() => null);
            throw new Error(payload?.error || t("backupExportFailed"));
        }
        await downloadBlob(await response.blob(), backupFilename(response));
        toast(t("exported"));
    } catch (error) {
        toast(error.message || t("backupExportFailed"));
    }
}

function renderClinicBackupCard() {
    const canExport = hasPermission("clinic_data.export");
    const canImport = hasPermission("clinic_data.import");
    if (!canExport && !canImport) return "";
    const result = state.backupImportResult;
    let resultHtml = "";
    if (result) {
        const total = Object.values(result.counts || {}).reduce((sum, value) => sum + value, 0);
        const skipped = Object.values(result.skipped || {}).reduce((sum, value) => sum + value, 0);
        resultHtml = `
          <div class="backup-result" role="status">
            <b>✅ ${t("backupImportDone")}</b>
            <span>${t("backupImportedRecords").replace("{count}", total)}</span>
            ${skipped ? `<span>${t("backupSkippedRecords").replace("{count}", skipped)}</span>` : ""}
            ${(result.unmatched_staff || []).length ? `<span>${t("backupUnmatchedStaff")}: <bdi dir="ltr">${result.unmatched_staff.map(esc).join(", ")}</bdi></span>` : ""}
          </div>`;
    }
    return `
      <div class="card backup-card">
        <div class="card-heading">
          <h2>💾 ${t("backup")}</h2>
        </div>
        ${canExport ? `
          <p class="muted">${t("backupExportHint")}</p>
          <div class="form-actions" style="justify-content:flex-start">
            <button class="button button-primary" type="button" data-action="export">⬇ ${t("backupExportButton")}</button>
          </div>` : ""}
        ${canImport ? `
          <hr class="backup-divider">
          <h3 class="backup-subtitle">${t("backupImportTitle")}</h3>
          <p class="backup-warning">⚠️ ${t("backupImportWarning")}</p>
          <form id="clinicImportForm" class="form-grid" autocomplete="off">
            <div class="field full-span">
              <label for="clinicImportFile">${t("backupImportFile")}</label>
              <input id="clinicImportFile" name="file" type="file" accept=".zip,application/zip" required>
            </div>
            <div class="field full-span">
              <label for="clinicImportPassword">${t("backupImportPassword")}</label>
              <input id="clinicImportPassword" name="password" type="password" required autocomplete="current-password" placeholder="••••••••">
            </div>
            <label class="backup-confirm full-span">
              <input type="checkbox" name="confirm" required>
              <span>${t("backupImportConfirm")}</span>
            </label>
            <div class="form-actions full-span" style="justify-content:flex-start">
              <button class="button btn-danger-ghost" type="submit" id="clinicImportButton">⬆ ${t("backupImportButton")}</button>
            </div>
          </form>
          ${resultHtml}` : ""}
      </div>`;
}

function bindClinicBackupEvents() {
    const form = $("#clinicImportForm");
    if (!form) return;
    form.onsubmit = async (event) => {
        event.preventDefault();
        const button = $("#clinicImportButton");
        const body = new FormData();
        const file = form.elements.file.files[0];
        if (!file) return;
        body.append("file", file);
        body.append("password", form.elements.password.value);
        button.disabled = true;
        button.textContent = t("backupImporting");
        try {
            const response = await window.AERODENT_API.post("/api/clinic/import", body);
            state.backupImportResult = response.data;
            toast(t("backupImportDone"));
            await refreshOnlineWorkspace();
        } catch (error) {
            state.backupImportResult = null;
            toast(error.status === 403 ? t("backupWrongPassword") : (error.message || t("backupImportFailed")));
            button.disabled = false;
            button.textContent = `⬆ ${t("backupImportButton")}`;
            form.elements.password.value = "";
        }
    };
}
