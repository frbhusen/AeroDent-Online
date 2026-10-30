// Clinic region: the country (decides how phone numbers are saved) and the currency, shared by the
// head doctor's Settings page and the Super Admin clinic forms. Online mode only.

const CURRENCY_PRESETS = ["SYR", "USD", "EUR", "SAR", "AED", "JOD", "EGP", "IQD", "KWD", "QAR", "TRY", "LBP"];
const CURRENCY_CUSTOM = "__custom";

async function ensureCountries() {
    if (state.countries?.length) return;
    try {
        const response = await window.AERODENT_API.get("/api/countries");
        state.countries = response.data || [];
    } catch (error) {
        state.countries = [];
    }
}

// Currency and country are needed by every role (amounts, WhatsApp/phone hints), but the full
// settings endpoint is head-doctor/doctor only, so this small profile is loaded for everyone.
async function loadClinicProfile() {
    if (!window.AERODENT_ONLINE) return;
    try {
        const response = await window.AERODENT_API.get("/api/clinic/profile");
        const profile = response.data || {};
        state.settings = {
            ...state.settings,
            currencySymbol: profile.currency || state.settings?.currencySymbol || "SYR",
            country: profile.country || null,
            ...(profile.name ? { clinicName: profile.name } : {}),
        };
    } catch (error) {
        // Keep the defaults; amounts then fall back to the default currency label.
    }
}

function countryByCode(code) {
    return (state.countries || []).find((country) => country.code === code) || null;
}

function countryName(country) {
    return currentLanguage === "ar" ? country.name_ar : country.name_en;
}

function phoneHintText(code) {
    const country = countryByCode(code);
    return country
        ? t("phoneAutoFormatHint").replace("{dial}", country.dial)
        : t("phoneNoCountryHint");
}

// Country select + currency select (presets or "Custom" with a text box) + a phone-format hint.
// The text input named "currency" always holds the real value, so forms can read it directly.
function regionFieldsHtml({ country = "", currency = "SYR", disabled = false } = {}) {
    const currentCurrency = currency || "SYR";
    const isCustom = !CURRENCY_PRESETS.includes(currentCurrency);
    const off = disabled ? "disabled" : "";
    const countryOptions = (state.countries || [])
        .map((item) => `<option value="${esc(item.code)}" ${item.code === country ? "selected" : ""}>${esc(countryName(item))} (+${esc(item.dial)})</option>`)
        .join("");
    const currencyOptions = CURRENCY_PRESETS
        .map((code) => `<option value="${code}" ${!isCustom && code === currentCurrency ? "selected" : ""}>${code}</option>`)
        .join("");
    return `
        <div class="field">
            <label>${t("country")}</label>
            <select name="country" ${off}>
                <option value="">${t("countryNotSet")}</option>
                ${countryOptions}
            </select>
        </div>
        <div class="field region-currency">
            <label>${t("currency")}</label>
            <select data-currency-preset ${off}>
                ${currencyOptions}
                <option value="${CURRENCY_CUSTOM}" ${isCustom ? "selected" : ""}>${t("currencyCustom")}</option>
            </select>
            <input name="currency" maxlength="10" value="${esc(currentCurrency)}" placeholder="${t("currencyCustomPlaceholder")}" ${isCustom ? "" : "hidden"} ${off}>
        </div>
        <small class="muted full-span" data-phone-hint>${phoneHintText(country)}</small>
    `;
}

function bindRegionFields(form) {
    const country = form?.querySelector('[name="country"]');
    const preset = form?.querySelector("[data-currency-preset]");
    const currency = form?.querySelector('[name="currency"]');
    const hint = form?.querySelector("[data-phone-hint]");
    if (!country || !preset || !currency) return;

    const showCustom = (custom) => {
        currency.hidden = !custom;
        if (custom) currency.focus();
    };
    preset.onchange = () => {
        if (preset.value === CURRENCY_CUSTOM) {
            showCustom(true);
        } else {
            currency.value = preset.value;
            showCustom(false);
        }
    };
    country.onchange = () => {
        if (hint) hint.textContent = phoneHintText(country.value);
        // Suggest the country's currency, unless a custom currency was typed.
        const suggested = countryByCode(country.value)?.currency;
        if (!suggested || preset.value === CURRENCY_CUSTOM) return;
        if (CURRENCY_PRESETS.includes(suggested)) {
            preset.value = suggested;
            currency.value = suggested;
            showCustom(false);
        } else {
            preset.value = CURRENCY_CUSTOM;
            currency.value = suggested;
            currency.hidden = false;
        }
    };
}
