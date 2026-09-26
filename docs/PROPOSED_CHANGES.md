# Proposed changes (branch `proposed-changes`)

These are improvements aimed at making AeroDent more competitive with established dental
practice software (Dentrix/Dentally/Curve/CareStack-style products). They live on the
`proposed-changes` branch only; `main` contains just the requested work and stability fixes.

> Branch name: the requested name `proposed changes` is not a valid git branch name (git refs
> cannot contain spaces), so the closest valid name, `proposed-changes`, is used.

Every proposal keeps the platform's rules: the backend is authoritative for permissions, all
data is clinic-scoped, and all new text is in English and Arabic through `web/i18n.js`.

## Implemented on this branch

### 1. Active sessions: "where am I signed in?"

**Why:** Clinic accounts are shared across front-desk PCs, doctors' phones and home laptops.
Competitors increasingly let users see and end their own sessions, which matters for a lost
phone, a shared computer or a departed employee. The server-side session table added on `main`
makes this cheap and exact.

**What:**
* `GET /api/auth/sessions`: the signed-in user's live sessions (device summary from the
  user agent, masked IP address, started / last active, "this device").
* `POST /api/auth/sessions/<id>/revoke`: sign out one of **your own** sessions (another user's
  session ID behaves exactly like a non-existent one).
* `POST /api/auth/sessions/revoke-others`: sign out everywhere else.
* Settings → *Active sessions* card (this device plus the five most recently active others, with
  a "+N more" line; *Sign out all other sessions* covers every one). Actions are audited
  (`session_revoked`, `sessions_revoked_others`).
* Settings is now shown to every clinic role. Secretaries previously had no Settings entry and
  so no way to change their own password in the UI; they now see only the security section
  (password and sessions), with clinic settings still hidden and still enforced server-side.

**Security:** Only the owner can list or revoke their sessions. IP addresses are shown masked
(last octet / last groups hidden). Session tokens are never exposed (only row IDs).

### 2. Patient recall list

**Why:** Recall (bringing patients back for check-ups/cleanings every N months) is the main
revenue driver in general dentistry and a standard feature of commercial systems. Today a clinic
has no way to see who is overdue.

**What:**
* `GET /api/patients/recall?months=6` (1–36): patients whose last completed visit (completed
  appointment or completed treatment) is older than N months **and** who have no upcoming
  booked appointment. Sorted by longest overdue, paginated, clinic-scoped, `patients.read`.
* Dashboard card *Due for recall* with the interval selector, each patient's last visit, and
  quick actions: open the patient, book an appointment, send a WhatsApp reminder (see 3).

### 3. One-tap WhatsApp reminders

**Why:** In the platform's main markets (Arabic-speaking clinics) patients are reached on
WhatsApp far more than by e-mail or SMS. Competitors charge for SMS gateways; a pre-filled
WhatsApp message needs no provider, no API key and no stored credentials.

**What:**
* A *WhatsApp* button on agenda appointments, dashboard upcoming visits and recall entries.
  It opens `https://wa.me/<number>?text=<message>` with a localized message (patient name, clinic,
  date and time for appointments; a check-up invitation for recalls). The staff member reviews
  and sends it from their own WhatsApp; nothing is sent automatically.
* Works in browsers and in the Android app (the link opens WhatsApp outside the app).
* Numbers must be stored in international format (`+963…` / `00963…`); otherwise the button is
  disabled and explains why, rather than guessing a country code.
* Appointment payloads now include `patient_phone` (every role that can read appointments can
  already read patients).

### Supporting change

`refreshOnlineWorkspace()` (page load / sign-in) now uses the same `loadViewData()` as
navigation instead of its own copy of the per-view loading logic, so data added to one path
(like the recall list) can never be missing from the other.

## Testing

`backend/test_proposed_features.py` covers session listing/masking, revoking your own vs.
another user's session (indistinguishable from a missing one), sign-out-others, CSRF/auth on the
session endpoints, recall selection rules (completed appointment or treatment, recent visits,
upcoming bookings, cancelled bookings, never-seen patients, other clinics), interval and
pagination validation, and month arithmetic. A browser pass checked the recall card, WhatsApp
links and messages (English/Arabic), the local-number explanation, the agenda button, the
sessions card and revoking a second device, at desktop and phone widths with no page errors.
The full existing suite (all backend suites, CSP, XSS, caching/tenant-isolation browser checks)
still passes on this branch.

## Proposed for later (not implemented)

| Proposal | Why it matters | Notes |
|---|---|---|
| Two-factor authentication (TOTP) | Expected by clinics handling health data; protects against password reuse. | Needs a `users.totp_secret` (encrypted at rest), enrolment with QR code, recovery codes, and a second login step. RFC 6238 can be implemented without new dependencies. |
| Online booking page | Patients book 24/7 from the clinic's website/Instagram; big conversion driver. | Public, rate-limited endpoint over the existing working-hours/slot logic; appointments land as `booked` pending confirmation; needs spam protection. |
| Revenue & production analytics | Owners compare doctors, procedures and months; standard in competitors. | Aggregations over treatments/invoices/payments; charts on the dashboard; CSV export. |
| Automated reminders (SMS/WhatsApp Business API) | Reduces no-shows without staff effort. | Requires a provider account, templates approved by Meta, opt-in tracking and a job scheduler. |
| Patient portal | Patients see appointments, invoices and prescriptions. | Separate patient accounts and a much stricter permission surface; worth doing after 2FA. |
| Insurance / claims | Needed in markets with dental insurance. | Country-specific; scope with target customers first. |
| iOS app | Same WebView-shell approach as Android. | Needs a Mac to build (WKWebView shell). |
