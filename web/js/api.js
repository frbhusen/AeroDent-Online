const AERODENT_MODE = new URLSearchParams(window.location.search).get("mode") || "online";
const AERODENT_ONLINE = AERODENT_MODE === "online";
const API_BASE_URL = window.AERODENT_API_BASE_URL
    || new URLSearchParams(window.location.search).get("api")
    || "";

class ApiError extends Error {
    constructor(message, status, payload = null) {
        super(message);
        this.name = "ApiError";
        this.status = status;
        this.payload = payload;
    }
}

async function apiRequest(path, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const isFormData = options.body instanceof FormData;
    const headers = new Headers(options.headers || {});

    if (!isFormData && options.body !== undefined) {
        headers.set("Content-Type", "application/json");
    }

    let response;
    try {
        response = await fetch(`${API_BASE_URL}${path}`, {
            ...options,
            method,
            headers,
            credentials: "include",
        });
    } catch (error) {
        throw new ApiError("Unable to reach the AeroDent server.", 0, error);
    }

    let payload = null;
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
        payload = await response.json().catch(() => null);
    } else if (response.status !== 204) {
        await response.text().catch(() => "");
    }

    if (!response.ok) {
        if (response.status === 401 && typeof window.handleOnlineUnauthorized === "function") {
            window.handleOnlineUnauthorized();
        }
        throw new ApiError(
            payload?.error || "The request could not be completed.",
            response.status,
            payload,
        );
    }

    return payload;
}

const api = {
    request: apiRequest,
    get: (path, options = {}) => apiRequest(path, { ...options, method: "GET" }),
    post: (path, body, options = {}) => apiRequest(path, {
        ...options,
        method: "POST",
        body: body instanceof FormData ? body : JSON.stringify(body),
    }),
    patch: (path, body, options = {}) => apiRequest(path, {
        ...options,
        method: "PATCH",
        body: body instanceof FormData ? body : JSON.stringify(body),
    }),
    put: (path, body, options = {}) => apiRequest(path, {
        ...options,
        method: "PUT",
        body: body instanceof FormData ? body : JSON.stringify(body),
    }),
    delete: (path, options = {}) => apiRequest(path, { ...options, method: "DELETE" }),
};

window.AERODENT_API = api;
window.AERODENT_ONLINE = AERODENT_ONLINE;