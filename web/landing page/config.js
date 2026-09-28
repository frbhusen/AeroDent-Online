/* ============================================================================
 * AeroDent Landing Page — Configuration
 * ----------------------------------------------------------------------------
 * This is the ONE place you edit to make the "14-day trial" form work.
 *
 * The trial form is delivered by Web3Forms (https://web3forms.com), a free
 * third-party service for static sites. It needs a single "access key".
 *
 * HOW TO SET IT UP (one-time, ~2 minutes):
 *   1. Go to https://web3forms.com
 *   2. Enter the destination email:  husen_.rajb@outlook.com
 *   3. Web3Forms emails you an "Access Key" (a UUID). Confirm the email.
 *   4. Paste that key below, replacing WEB3FORMS_ACCESS_KEY_PLACEHOLDER.
 *
 * SECURITY NOTE: A Web3Forms access key is designed to be public and safe to
 * ship in client-side code — it only authorises delivering a form submission
 * to the fixed email you registered. It is NOT a secret/API password and it
 * cannot be used to read submissions. No other secrets belong in this file.
 *
 * Until a real key is set, the form stays fully usable and validated, but on
 * submit it shows a clear "not configured yet" message instead of failing
 * silently. See landing page/README.md for full details.
 * ========================================================================== */

window.AERODENT_LANDING_CONFIG = {
  // Paste your Web3Forms access key here (see instructions above).
  web3formsAccessKey: "840d00bc-e564-4c4c-a824-07ae13df8aeb",

  // Where submissions are delivered. Web3Forms uses the email registered to
  // the access key above; this value is only used to label the email subject.
  destinationEmail: "husen_.rajb@outlook.com",

  // Endpoint — do not change unless Web3Forms changes their API.
  web3formsEndpoint: "https://api.web3forms.com/submit",

  // Subject line for the delivered email.
  emailSubject: "طلب تجربة AeroDent لمدة 14 يومًا — AeroDent 14-day trial request",

  // English is architecturally supported but not yet fully translated.
  // Set to true once the English dictionary in i18n.js is completed.
  englishEnabled: false,
};
