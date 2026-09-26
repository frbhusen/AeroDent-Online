async function exportData() {
    if (window.AERODENT_ONLINE) {
        try {
            const response = await window.AERODENT_API.get("/api/clinic/export");
            const clinic = response.data?.clinic;
            const blob = new Blob([JSON.stringify(response.data, null, 2)], { type: "application/json" });
            const link = document.createElement("a");
            link.href = URL.createObjectURL(blob);
            link.download = `aerodent_clinic_${clinic?.id || "export"}_${today()}.json`;
            link.click();
            URL.revokeObjectURL(link.href);
            toast(t("exported") || "Clinic data exported");
        } catch (error) {
            toast(error.message || "Failed to export clinic data");
        }
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