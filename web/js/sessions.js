// "Active sessions" card in Settings (online mode): the signed-in user's own sessions, with
// the option to sign out other devices. The server only ever returns and revokes the caller's
// own sessions; see /api/auth/sessions and docs/PROPOSED_CHANGES.md.

const SESSIONS_SHOWN = 5;

async function loadActiveSessions() {
    if (!window.AERODENT_ONLINE) return;
    try {
        const response = await window.AERODENT_API.get("/api/auth/sessions");
        state.activeSessions = response.sessions || [];
        state.activeSessionsError = "";
    } catch (error) {
        state.activeSessionsError = error.message;
    }
}

function sessionDeviceLabel(device) {
    if (device?.app) return `📱 ${t("sessionAndroidApp")}`;
    const parts = [device?.browser, device?.os].filter(Boolean);
    const icon = device?.os === "Android" || device?.os === "iOS" ? "📱" : "💻";
    return `${icon} ${parts.length ? parts.map(esc).join(" · ") : t("sessionUnknownDevice")}`;
}

function sessionTime(iso) {
    const value = new Date(iso);
    if (Number.isNaN(value.getTime())) return "";
    return value.toLocaleString(currentLanguage === "ar" ? "ar-u-ca-gregory-nu-latn" : "en-GB", {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
    });
}

function renderActiveSessionsCard() {
    if (!window.AERODENT_ONLINE) return "";
    const sessions = state.activeSessions || [];
    const others = sessions.filter((item) => !item.current);
    // The current device first, then the most recently active others; "sign out all other
    // sessions" still covers the ones not listed.
    const shown = [...sessions.filter((item) => item.current), ...others.slice(0, SESSIONS_SHOWN)];
    const hidden = sessions.length - shown.length;
    const rows = state.activeSessionsError
        ? `<p class="muted">${esc(state.activeSessionsError)}</p>`
        : shown.map((item) => `
            <div class="session-row ${item.current ? "is-current" : ""}">
                <div class="session-info">
                    <b>${sessionDeviceLabel(item.device)}</b>
                    <small class="muted">
                        ${item.current ? `<span class="badge badge-green">${t("sessionThisDevice")}</span>` : ""}
                        ${t("sessionLastActive")}: <bdi dir="ltr">${esc(sessionTime(item.last_seen_at))}</bdi>
                        ${item.ip ? ` · <bdi dir="ltr">${esc(item.ip)}</bdi>` : ""}
                    </small>
                </div>
                ${item.current ? "" : `<button type="button" class="button button-ghost button-sm" data-revoke-session="${Number(item.id)}">${t("sessionSignOut")}</button>`}
            </div>`).join("") + (hidden > 0 ? `<p class="muted sessions-more">${t("sessionsMore").replace("{count}", hidden)}</p>` : "");

    return `
      <div class="card sessions-card">
        <div class="card-heading">
          <h2>🖥️ ${t("activeSessions")}</h2>
          ${others.length ? `<button type="button" class="button button-ghost" id="revokeOtherSessionsBtn">${t("sessionSignOutOthers")}</button>` : ""}
        </div>
        <p class="muted sessions-hint">${t("activeSessionsHint")}</p>
        <div class="session-list">${rows}</div>
      </div>`;
}

function bindActiveSessionEvents() {
    $$("[data-revoke-session]").forEach((button) => {
        button.onclick = async () => {
            button.disabled = true;
            try {
                await window.AERODENT_API.post(`/api/auth/sessions/${Number(button.dataset.revokeSession)}/revoke`, {});
                toast(t("sessionRevoked"));
            } catch (error) {
                toast(error.message);
            }
            await loadActiveSessions();
            render();
        };
    });
    const others = $("#revokeOtherSessionsBtn");
    if (others) {
        others.onclick = async () => {
            if (!confirm(t("sessionSignOutOthersConfirm"))) return;
            others.disabled = true;
            try {
                await window.AERODENT_API.post("/api/auth/sessions/revoke-others", {});
                toast(t("sessionsRevoked"));
            } catch (error) {
                toast(error.message);
            }
            await loadActiveSessions();
            render();
        };
    }
}
