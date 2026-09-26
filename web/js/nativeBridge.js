// Integration with the AeroDent Android shell (mobile/android). See docs/MOBILE.md.
//
// The shell exposes `window.AeroDentNative` only to pages served from the configured AeroDent
// server origin (WebViewCompat.addWebMessageListener with an origin allow-list). In a normal
// browser the object does not exist and every helper below falls back to standard web APIs,
// so this file changes nothing outside the app.
//
// The channel carries no credentials: the session stays in the HttpOnly cookie, which the page
// can never read. It is used only for what a WebView cannot do by itself: saving generated
// files (blob:/data: downloads) and printing.

const NativeShell = (() => {
    const channel = window.AeroDentNative;
    const available = !!(channel && typeof channel.postMessage === "function");
    const pending = new Map();
    let nextId = 1;

    if (available) {
        document.documentElement.classList.add("native-app");
        channel.addEventListener("message", (event) => {
            let message;
            try {
                message = JSON.parse(event.data);
            } catch (_) {
                return;
            }
            const entry = pending.get(message?.id);
            if (!entry) return;
            pending.delete(message.id);
            if (message.ok) entry.resolve(message);
            else entry.reject(new Error(message.error || "native-error"));
        });
    }

    function request(payload) {
        return new Promise((resolve, reject) => {
            const id = nextId++;
            pending.set(id, { resolve, reject });
            channel.postMessage(JSON.stringify({ ...payload, id }));
        });
    }

    function blobToBase64(blob) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
            reader.onerror = () => reject(reader.error);
            reader.readAsDataURL(blob);
        });
    }

    async function saveBlob(blob, filename) {
        const data = await blobToBase64(blob);
        return request({
            type: "download",
            name: filename || "aerodent-file",
            mime: blob.type || "application/octet-stream",
            data,
        });
    }

    function print(jobName) {
        return request({ type: "print", name: jobName || document.title || "AeroDent" });
    }

    return { available, saveBlob, print };
})();

// Saves a generated file. In the Android app it is written to the device's Downloads folder;
// in a browser it uses a normal download link.
async function downloadBlob(blob, filename) {
    if (NativeShell.available) {
        try {
            await NativeShell.saveBlob(blob, filename);
            toast(t("fileSavedToDownloads"));
        } catch (_) {
            toast(t("fileSaveFailed"));
        }
        return;
    }
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.style.display = "none";
    document.body.append(link);
    link.click();
    link.remove();
    // Revoking immediately can cancel the download in some browsers; give it time to start.
    setTimeout(() => URL.revokeObjectURL(link.href), 60_000);
}

// Prints the current page (print CSS applies). Resolves once the print dialog is done.
function printPage(jobName) {
    if (NativeShell.available) {
        return NativeShell.print(jobName).catch(() => toast(t("printFailed")));
    }
    window.print();
    return Promise.resolve();
}

if (NativeShell.available) {
    // Links that download generated content (blob:/data: URLs) cannot be fetched by the
    // Android download manager, so hand them to the shell instead. The page's CSP does not
    // allow fetch() of blob: URLs, so remember the Blob behind each object URL instead.
    const objectUrlBlobs = new Map();
    const createObjectURL = URL.createObjectURL.bind(URL);
    const revokeObjectURL = URL.revokeObjectURL.bind(URL);
    URL.createObjectURL = (object) => {
        const url = createObjectURL(object);
        if (object instanceof Blob) objectUrlBlobs.set(url, object);
        return url;
    };
    URL.revokeObjectURL = (url) => {
        // Keep the Blob a little longer: the click that uses it may still be in progress.
        setTimeout(() => objectUrlBlobs.delete(url), 60_000);
        revokeObjectURL(url);
    };

    const blobFromDataUrl = (href) => {
        const match = /^data:([^;,]*)(;base64)?,(.*)$/is.exec(href);
        if (!match) return null;
        const text = match[2] ? atob(match[3]) : decodeURIComponent(match[3]);
        const bytes = Uint8Array.from(text, (ch) => ch.charCodeAt(0));
        return new Blob([bytes], { type: match[1] || "application/octet-stream" });
    };

    document.addEventListener(
        "click",
        (event) => {
            const link = event.target.closest?.("a[download]");
            if (!link || !/^(blob|data):/i.test(link.href)) return;
            event.preventDefault();
            const blob = link.href.startsWith("blob:") ? objectUrlBlobs.get(link.href) : blobFromDataUrl(link.href);
            if (!blob) {
                toast(t("fileSaveFailed"));
                return;
            }
            downloadBlob(blob, link.getAttribute("download") || "aerodent-file");
        },
        true,
    );
}

// Called by the Android shell when the system Back button is pressed. Closes the topmost
// overlay first, then returns to the dashboard. Returns false when there is nothing left to
// close, so the shell can leave the app.
window.AeroDentBack = function aeroDentBack() {
    const palette = document.querySelector("#commandPaletteModal.show");
    if (palette && typeof closeCommandPalette === "function") {
        closeCommandPalette();
        return true;
    }
    const modal = document.querySelector("#modal.show");
    if (modal) {
        modal.classList.remove("show");
        return true;
    }
    if (document.body.classList.contains("drawer-open")) {
        document.body.classList.remove("drawer-open");
        return true;
    }
    const signedIn = !!state?.auth?.user;
    if (signedIn && state.view && state.view !== "dashboard" && typeof navigateTo === "function") {
        navigateTo("dashboard");
        return true;
    }
    return false;
};

// Connectivity banner (online mode only). Nothing is queued while offline: the banner tells
// the user plainly that changes cannot be saved until the connection returns.
(function watchConnectivity() {
    if (!window.AERODENT_ONLINE) return;
    let banner = null;
    function show() {
        if (banner) return;
        banner = document.createElement("div");
        banner.className = "connection-banner";
        banner.setAttribute("role", "status");
        banner.textContent = t("connectionLost");
        document.body.append(banner);
    }
    function hide() {
        if (!banner) return;
        banner.remove();
        banner = null;
        toast(t("connectionRestored"));
        if (state?.auth?.user && typeof loadViewData === "function") {
            loadViewData(state.view);
        }
    }
    window.addEventListener("offline", show);
    window.addEventListener("online", hide);
    if (navigator.onLine === false) {
        document.addEventListener("DOMContentLoaded", show, { once: true });
    }
})();
