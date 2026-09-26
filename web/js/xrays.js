let onlineXrayRequest = 0;

function mapApiXray(item) {
    return {
        ...item,
        patientId: item.patient_id,
        toothTag: item.tooth_tag,
        imageUrl: `${API_BASE_URL}/api/x-rays/${item.id}/file`,
        downloadUrl: `${API_BASE_URL}/api/x-rays/${item.id}/file`,
        createdAt: item.created_at,
        updatedAt: item.updated_at,
    };
}

function selectedXrayPatient() {
    const patient = state.selectedPatient;
    return Number.isInteger(patient?.id) && patient.id > 0 ? patient : null;
}

function canModifyXrays() {
    return !window.AERODENT_ONLINE || (
        hasPermission("xrays.create") &&
        hasPermission("xrays.update") &&
        hasPermission("xrays.delete")
    );
}

async function loadOnlineXrays() {
    if (!window.AERODENT_ONLINE) return;
    const requestId = ++onlineXrayRequest;
    const patient = selectedXrayPatient();
    if (!patient) {
        state.xrayLoading = false;
        state.xrayReadOnly = false;
        state.xrays = [];
        state.xrayError = "";
        render();
        return;
    }

    const patientId = patient.id;
    state.xrayLoading = true;
    state.xrayReadOnly = !hasPermission("xrays.update");
    state.xrayError = "";
    render();

    try {
        const response = await window.AERODENT_API.get(`/api/patients/${patientId}/x-rays`);
        if (requestId !== onlineXrayRequest || selectedXrayPatient()?.id !== patientId) return;
        state.xrays = (response.data || []).map(mapApiXray);
    } catch (error) {
        if (requestId !== onlineXrayRequest || selectedXrayPatient()?.id !== patientId) return;
        state.xrayReadOnly = error.status === 403;
        state.xrayError = error.message || "Failed to load X-rays.";
        if (error.status === 404) state.xrays = [];
    } finally {
        if (requestId === onlineXrayRequest && selectedXrayPatient()?.id === patientId) {
            state.xrayLoading = false;
            render();
        }
    }
}

function renderXrays() {
    const patient = selectedXrayPatient();
    const images = window.AERODENT_ONLINE
        ? state.xrays
        : state.xrays.filter((item) => item.patientId === patient?.id);

    const editable = patient && canModifyXrays();
    const readOnly = window.AERODENT_ONLINE && patient && !editable ? `<p class="muted">${t("readOnly")}</p>` : "";

    let uploadFormHtml = "";
    if (patient) {
        if (editable) {
            uploadFormHtml = `
                <div class="xray-upload-form">
                    <div class="field">
                        <label>${t("xrayType")}</label>
                        <select id="xrayType">
                            <option value="periapical">${t("periapical")}</option>
                            <option value="bitewing">${t("bitewing")}</option>
                            <option value="panoramic">${t("panoramic")}</option>
                            <option value="cephalometric">${t("cephalometric")}</option>
                            <option value="cbct">${t("cbct")}</option>
                            <option value="other">${t("other")}</option>
                        </select>
                    </div>
                    <div class="field">
                        <label>${t("toothNumber")}</label>
                        <input id="xrayToothNumber" type="number" min="1" max="85" placeholder="${t("toothNumber")}">
                    </div>
                    <div class="field full-span">
                        <label>${t("clinicalNotes")}</label>
                        <textarea id="xrayNotes" rows="2" placeholder="${t("clinicalNotes")}"></textarea>
                    </div>
                    <label class="button button-primary">
                        ＋ ${t("upload")}
                        <input id="xrayUpload" type="file" accept="image/*" hidden>
                    </label>
                </div>
            `;
        } else {
            uploadFormHtml = readOnly;
        }
    } else {
        uploadFormHtml = `<p class="muted">${t("selectPatient")}</p>`;
    }

    let gridHtml = "";
    if (state.xrayLoading) {
        gridHtml = `<p class="muted">${t("loading")}</p>`;
    } else if (state.xrayError) {
        gridHtml = `<p class="login-error">${esc(state.xrayError)}</p>`;
    } else if (images.length) {
        gridHtml = images.map((item) => {
            const imgSrc = window.AERODENT_ONLINE ? item.imageUrl : item.base64Data;
            return `
                <div class="xray-item xray-item-clickable" data-open-xray="${item.id}">
                    <img src="${imgSrc}" alt="${esc(item.filename)}" loading="lazy">
                    <div class="xray-info">
                        <div>
                            <b>${esc(item.filename)}</b>
                            <div class="xray-meta">
                                <span>${t(item.type || "other")}</span>
                                ${item.toothTag ? `<span>${t("toothNumber")} #${esc(item.toothTag)}</span>` : ""}
                                <span>${formatXrayTimestamp(item)}</span>
                            </div>
                            ${item.notes ? `<p class="xray-notes">${esc(item.notes)}</p>` : ""}
                        </div>
                        ${editable ? `
                            <button type="button" class="xray-delete-button" data-delete-xray="${item.id}" title="${t("deleteXray")}" aria-label="${t("deleteXray")}">×</button>
                        ` : ""}
                    </div>
                </div>
            `;
        }).join("");
    } else {
        gridHtml = `<p class="muted">${t("noVisits")}</p>`;
    }

    return `
        <section class="card">
            <div class="card-heading">
                <div>
                    <h2>${t("xrays")}</h2>
                    <p class="muted">${images.length} ${window.AERODENT_ONLINE ? t("savedOnline") : t("saved")}</p>
                </div>
            </div>

            ${patientSelector("xrayPatientSelect", patient)}
            ${uploadFormHtml}

            <div class="xray-grid">
                ${gridHtml}
            </div>
        </section>
    `;
}

function formatXrayTimestamp(xray) {
    return [xray.date, xray.time]
        .filter(Boolean)
        .map((value) => esc(value))
        .join(" · ");
}

async function editXray(xrayId) {
    let xray = (state.xrays || []).find((item) => item.id === xrayId);
    if (!xray && window.AERODENT_ONLINE) {
        try {
            const res = await window.AERODENT_API.get(`/api/x-rays/${xrayId}`);
            if (res && res.data) {
                xray = mapApiXray(res.data);
                if (!Array.isArray(state.xrays)) state.xrays = [];
                state.xrays.push(xray);
            }
        } catch (e) {
            // ignore
        }
    } else if (!xray && !window.AERODENT_ONLINE) {
        try {
            xray = await dbGet("xrays", xrayId);
        } catch (e) {
            // ignore
        }
    }
    if (!xray || !canModifyXrays()) return;

    modal(
        t("edit"),
        `<form id="xrayEditForm" class="form-grid">
            <div class="field full-span">
                <label>${t("xrayName")}</label>
                <input name="filename" value="${esc(xray.filename || "")}" required>
            </div>
            <div class="field">
                <label>${t("date")}</label>
                <input type="date" name="date" value="${esc(xray.date || today())}" required>
            </div>
            <div class="field">
                <label>${t("xrayType")}</label>
                <select name="type">
                    <option value="periapical" ${xray.type === "periapical" ? "selected" : ""}>${t("periapical")}</option>
                    <option value="bitewing" ${xray.type === "bitewing" ? "selected" : ""}>${t("bitewing")}</option>
                    <option value="panoramic" ${xray.type === "panoramic" ? "selected" : ""}>${t("panoramic")}</option>
                    <option value="cephalometric" ${xray.type === "cephalometric" ? "selected" : ""}>${t("cephalometric")}</option>
                    <option value="cbct" ${xray.type === "cbct" ? "selected" : ""}>${t("cbct")}</option>
                    <option value="other" ${!xray.type || xray.type === "other" ? "selected" : ""}>${t("other")}</option>
                </select>
            </div>
            <div class="field">
                <label>${t("time")}</label>
                <input type="time" name="time" value="${esc(xray.time || "")}">
            </div>
            <div class="form-actions full-span">
                <button type="button" class="button button-ghost" id="cancelXrayEdit">${t("cancel")}</button>
                <button class="button button-primary" type="submit">${t("save")}</button>
            </div>
        </form>`
    );

    $("#cancelXrayEdit").onclick = () => openXrayViewer(xrayId);

    $("#xrayEditForm").onsubmit = async (event) => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(event.target));

        if (window.AERODENT_ONLINE) {
            try {
                const payload = {
                    filename: data.filename.trim(),
                    date: data.date,
                    type: data.type || "other",
                    time: data.time || null,
                };
                const res = await window.AERODENT_API.patch(`/api/x-rays/${xray.id}`, payload);
                const updatedXray = mapApiXray(res.data);
                const index = state.xrays.findIndex((item) => item.id === xray.id);
                if (index !== -1) {
                    state.xrays[index] = updatedXray;
                } else {
                    state.xrays.push(updatedXray);
                }
                if (state.selectedPatient?.id && typeof loadOnlinePatientTimeline === "function") {
                    await loadOnlinePatientTimeline(state.selectedPatient.id);
                }
                render();
                await openXrayViewer(xrayId);
                toast(t("savedOnline"));
            } catch (error) {
                toast(error.message || "Failed to update X-ray.");
            }
            return;
        }

        await dbPut("xrays", {
            ...xray,
            filename: data.filename.trim(),
            date: data.date,
            type: data.type || "other",
            time: data.time,
        });

        await refresh();
        await openXrayViewer(xrayId);
    };
}

let openingXrayId = null;

async function openXrayViewer(xrayId) {
    if (!xrayId) return;
    if (openingXrayId === xrayId) return;

    let xray = (state.xrays || []).find((item) => item.id === xrayId);

    if (!xray) {
        openingXrayId = xrayId;
        try {
            if (window.AERODENT_ONLINE) {
                const response = await window.AERODENT_API.get(`/api/x-rays/${xrayId}`);
                if (response && response.data) {
                    xray = mapApiXray(response.data);
                    if (!Array.isArray(state.xrays)) state.xrays = [];
                    const existingIndex = state.xrays.findIndex((item) => item.id === xray.id);
                    if (existingIndex >= 0) {
                        state.xrays[existingIndex] = xray;
                    } else {
                        state.xrays.push(xray);
                    }
                }
            } else {
                xray = await dbGet("xrays", xrayId);
            }
        } catch (error) {
            console.error("Failed to load X-ray details:", error);
            toast(error.message || t("xrayNotFound") || "Failed to load X-ray.");
            return;
        } finally {
            openingXrayId = null;
        }
    }

    if (!xray) {
        toast(t("xrayNotFound") || "X-ray not found.");
        return;
    }

    const imgSrc = window.AERODENT_ONLINE ? xray.imageUrl : xray.base64Data;
    const downloadSrc = window.AERODENT_ONLINE ? xray.downloadUrl : xray.base64Data;
    const editable = canModifyXrays();

    modal(
        xray.filename || t("xrays"),
        `<div class="xray-viewer">
            <div class="xray-viewer-toolbar">
                <div class="xray-viewer-info">
                    <span class="badge">${t(xray.type || "other")}</span>
                    ${xray.toothTag ? `<span class="badge">${t("toothNumber")} #${esc(xray.toothTag)}</span>` : ""}
                    <span class="muted">${formatXrayTimestamp(xray)}</span>
                </div>
                <div class="xray-viewer-actions">
                    ${editable ? `<button type="button" class="button button-ghost" id="xrayEdit">${t("edit")}</button>` : ""}
                    <button type="button" class="button button-ghost" id="xrayZoomOut">−</button>
                    <span id="xrayZoomLabel" class="xray-zoom-label">100%</span>
                    <button type="button" class="button button-ghost" id="xrayZoomIn">+</button>
                    <button type="button" class="button button-ghost" id="xrayReset">${t("reset")}</button>
                    <button type="button" class="button button-ghost" id="xrayRotate">↻</button>
                    <a class="button button-primary" id="xrayDownload" href="${downloadSrc}" download="${esc(xray.filename || "xray.webp")}" target="_blank">
                        ${t("download")}
                    </a>
                </div>
            </div>

            <div class="xray-viewer-stage" id="xrayViewerStage">
                <img id="xrayViewerImage" src="${imgSrc}" alt="${esc(xray.filename || "X-ray")}" draggable="false">
            </div>

            ${xray.notes ? `
                <div class="xray-viewer-notes">
                    <strong>${t("clinicalNotes")}</strong>
                    <p>${esc(xray.notes)}</p>
                </div>
            ` : ""}
        </div>`
    );

    const image = $("#xrayViewerImage");
    const stage = $("#xrayViewerStage");
    const download = $("#xrayDownload");
    const zoomLabel = $("#xrayZoomLabel");

    if (!image || !stage || !download || !zoomLabel) return;

    let zoom = 1;
    let rotation = 0;
    let panX = 0;
    let panY = 0;
    let isPanning = false;
    let activePointerId = null;
    let panStartX = 0;
    let panStartY = 0;

    function constrainPan() {
        const angle = (rotation * Math.PI) / 180;
        const cosine = Math.abs(Math.cos(angle));
        const sine = Math.abs(Math.sin(angle));
        const rotatedWidth = (image.offsetWidth * cosine + image.offsetHeight * sine) * zoom;
        const rotatedHeight = (image.offsetWidth * sine + image.offsetHeight * cosine) * zoom;
        const maxPanX = Math.max(0, (rotatedWidth - stage.clientWidth) / 2);
        const maxPanY = Math.max(0, (rotatedHeight - stage.clientHeight) / 2);
        panX = Math.max(-maxPanX, Math.min(maxPanX, panX));
        panY = Math.max(-maxPanY, Math.min(maxPanY, panY));
    }

    function updateViewer() {
        if (zoom <= 1) {
            panX = 0;
            panY = 0;
        } else {
            constrainPan();
        }
        image.style.transform = `translate(${panX}px, ${panY}px) scale(${zoom}) rotate(${rotation}deg)`;
        zoomLabel.textContent = `${Math.round(zoom * 100)}%`;
        stage.classList.toggle("is-pannable", zoom > 1);
    }

    function setZoom(nextZoom) {
        zoom = Math.max(0.5, Math.min(4, nextZoom));
        updateViewer();
    }

    function stopPanning() {
        if (activePointerId !== null && stage.hasPointerCapture(activePointerId)) {
            stage.releasePointerCapture(activePointerId);
        }
        isPanning = false;
        activePointerId = null;
    }

    stage.addEventListener("pointerdown", (event) => {
        if (zoom <= 1) return;
        isPanning = true;
        activePointerId = event.pointerId;
        panStartX = event.clientX - panX;
        panStartY = event.clientY - panY;
        stage.setPointerCapture(event.pointerId);
    });

    stage.addEventListener("pointermove", (event) => {
        if (!isPanning || event.pointerId !== activePointerId) return;
        panX = event.clientX - panStartX;
        panY = event.clientY - panStartY;
        constrainPan();
        image.style.transform = `translate(${panX}px, ${panY}px) scale(${zoom}) rotate(${rotation}deg)`;
    });

    stage.addEventListener("pointerup", stopPanning);
    stage.addEventListener("pointercancel", stopPanning);
    stage.addEventListener("lostpointercapture", stopPanning);

    stage.addEventListener("wheel", (event) => {
        event.preventDefault();
        if (event.deltaY === 0) return;
        setZoom(zoom + (event.deltaY < 0 ? 0.25 : -0.25));
    }, { passive: false });

    $("#xrayZoomIn").onclick = () => setZoom(zoom + 0.25);
    $("#xrayZoomOut").onclick = () => setZoom(zoom - 0.25);
    $("#xrayReset").onclick = () => {
        zoom = 1;
        rotation = 0;
        panX = 0;
        panY = 0;
        updateViewer();
    };
    $("#xrayRotate").onclick = () => {
        rotation = (rotation + 90) % 360;
        updateViewer();
    };

    if (editable && $("#xrayEdit")) {
        $("#xrayEdit").onclick = () => editXray(xrayId);
    }

    updateViewer();
}

async function handleXrayUploadFile(file) {
    if (!file) return;

    if (!file.type.startsWith("image/")) {
        toast(t("unableProcessXray"));
        return;
    }

    const MAX_SOURCE_BYTES = 15 * 1024 * 1024;
    if (file.size > MAX_SOURCE_BYTES) {
        toast("Image is too large (max 15MB).");
        return;
    }

    const patient = selectedXrayPatient();
    if (!patient) {
        toast(t("selectPatientFirst"));
        return;
    }

    if (!canModifyXrays()) return;

    const xrayType = $("#xrayType")?.value || "other";
    const toothNumber = Number($("#xrayToothNumber")?.value) || null;
    const notes = $("#xrayNotes")?.value.trim() || "";

    if (window.AERODENT_ONLINE) {
        if (state.xraySaving) return;
        state.xraySaving = true;
        try {
            const formData = new FormData();
            formData.append("file", file);
            formData.append("type", xrayType);
            if (toothNumber) formData.append("tooth_tag", String(toothNumber));
            if (notes) formData.append("notes", notes);
            formData.append("date", today());
            formData.append("time", new Date().toTimeString().slice(0, 5));

            await window.AERODENT_API.post(`/api/patients/${patient.id}/x-rays`, formData);
            await loadOnlineXrays();
            toast(t("xrayUploaded") || "X-ray uploaded successfully.");
        } catch (error) {
            toast(error.message || "Failed to upload X-ray.");
        } finally {
            state.xraySaving = false;
        }
        return;
    }

    try {
        const compressed = await compressXray(file);
        const base64Data = await blobToBase64(compressed);
        await dbPut("xrays", {
            patientId: patient.id,
            filename: file.name,
            base64Data,
            date: today(),
            time: new Date().toTimeString().slice(0, 5),
            type: xrayType,
            toothTag: toothNumber,
            notes,
        });
        await refresh();
        toast(t("xrayUploaded"));
    } catch (error) {
        console.error("X-ray upload failed:", error);
        toast(t("unableProcessXray"));
    }
}

async function deleteXrayRecord(xrayId) {
    if (!canModifyXrays()) return;
    if (!confirm(t("deleteXray") + "?")) return;

    if (window.AERODENT_ONLINE) {
        if (state.xraySaving) return;
        state.xraySaving = true;
        try {
            await window.AERODENT_API.delete(`/api/x-rays/${xrayId}`);
            state.xrays = state.xrays.filter((item) => item.id !== xrayId);
            if (state.selectedPatient?.id && typeof loadOnlinePatientTimeline === "function") {
                await loadOnlinePatientTimeline(state.selectedPatient.id);
            }
            render();
            toast(t("savedOnline"));
        } catch (error) {
            toast(error.message || "Failed to delete X-ray.");
        } finally {
            state.xraySaving = false;
        }
        return;
    }

    try {
        const xray = await dbGet("xrays", xrayId);
        if (!xray) return;
        await dbDelete("xrays", xrayId);
        await refresh();
        showUndo(t("deleteXray"), async () => {
            await dbPut("xrays", xray);
            await refresh();
        });
    } catch (error) {
        console.error("X-ray deletion failed:", error);
        toast(t("unableDeleteXray") || "Unable to delete X-ray.");
    }
}

async function compressXray(file) {
    const bitmap = await createImageBitmap(file);
    const maxWidth = 1600;
    const maxHeight = 1600;
    const scale = Math.min(1, maxWidth / bitmap.width, maxHeight / bitmap.height);
    const width = Math.round(bitmap.width * scale);
    const height = Math.round(bitmap.height * scale);

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;

    const context = canvas.getContext("2d");
    if (!context) throw new Error("Could not create canvas context.");

    context.drawImage(bitmap, 0, 0, width, height);

    return new Promise((resolve, reject) => {
        canvas.toBlob((blob) => {
            if (!blob) {
                reject(new Error("Image compression failed."));
                return;
            }
            resolve(blob);
        }, "image/webp", 0.82);
    });
}

function blobToBase64(blob) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(new Error("Could not read compressed image."));
        reader.readAsDataURL(blob);
    });
}
