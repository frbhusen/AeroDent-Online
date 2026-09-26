# AeroDent Online — Audit & Hardening Plan

> **For agentic workers:** This is a bug-fix/hardening backlog against an existing, mostly-working
> app, not a greenfield feature. Tasks are independent (different files/subsystems); implement
> task-by-task with superpowers:executing-plans style discipline (test first where feasible, run
> the real backend test suite after each backend task, commit after each task). No cross-task
> Interfaces/Consumes/Produces sections are needed — each task stands alone.

**Goal:** Fix the confirmed correctness/security/financial bugs found by a full audit of the
existing Flask + vanilla-JS multi-tenant dental clinic app, without changing its architecture,
UX, or online/offline separation.

**Architecture:** Unchanged. Flask REST API + SQLAlchemy + PostgreSQL (online), IndexedDB + Web
Crypto PIN (offline). No new frameworks, no schema rewrites beyond one additive migration if
needed.

**Tech Stack:** Python 3 / Flask / Flask-SQLAlchemy / Flask-Migrate / PostgreSQL / psycopg;
vanilla JS frontend.

**Spec:** The user's pasted 54-section audit brief (this session's first message) + the findings
below, gathered by directly reading the code and by running the existing test suite against a
freshly migrated local Postgres DB (`aerodent_dev` / `aerodent_test`).

## Baseline (verified before any changes)

- `flask --app backend.app db upgrade` runs clean end-to-end on an empty DB (all 9 migrations
  apply in order, no drift).
- Full backend test suite (17 files): **15 pass, 2 fail.**
  - `backend/test_patients.py` fails at line 216: secretary DELETE on a patient returns 200, not
    the expected 403.
  - `backend/test_permissions.py` fails at line 261: `user_has_permission` for `secretary`
    doesn't match `EXPECTED_PERMISSIONS["secretary"]` (test's own encoded spec has no
    `patients.delete` for secretary; code grants it).
  - Root cause of both: `backend/auth/permissions.py:134` — `"patients.delete"` is present in the
    `secretary` role's permission set. This is a real, currently-shipping authorization bug (spec
    §9 says secretary should not be able to delete patients).
- `node --check` on every file under `web/**/*.js`: all pass, no syntax errors.

## Global Constraints

- Never weaken clinic_id scoping or composite FK tenant isolation.
- Never accept client-supplied `clinic_id`/`user_id`/`role`/`created_by` for authorization.
- Financial fields (`amount`, `discount`, `paid_amount`, `balance`, `status`) stay
  server-computed; reject invalid input with 4xx rather than silently coercing it.
- Keep vanilla JS architecture; no new frameworks/build steps.
- Every backend behavior change must be proven by the existing suite plus a new targeted test
  when no test currently covers it; run `python -m backend.test_X` (DATABASE_URL pointed at
  `aerodent_test`) after each backend task, and the full suite before final commit of that area.
- Preserve i18n (already at 100% en/ar parity per audit — don't introduce new hardcoded strings).

## Review Focus

1. Overpayment on `POST /api/invoices/<id>/payments` — a payment can be recorded that pushes
   `paid_amount` above the invoice's payable amount even though the sibling invoice-PATCH path
   already rejects this; a reasonable engineer expects both paths to enforce the same invariant.
2. Concurrent payment requests against the same invoice — no row lock exists; two simultaneous
   payments can race and corrupt `paid_amount`/`balance`.
3. Cross-clinic `doctor_id` on waitlist auto-fill — an attacker or buggy client can crash the
   request (uncaught 500 via FK violation) instead of getting a clean 4xx.
4. Patient-switch while already on the Prescriptions or X-rays screen — the previous patient's
   data stays on screen because the dropdown's `onchange` never reloads it.
5. A busy clinic's weekly appointment view silently drops appointments beyond the 100th instead
   of erroring or paginating — a reasonable user assumes the calendar shows everything that week.

---

### Task 1: Fix secretary patient-delete permission (confirmed by 2 failing tests)

**Files:**
- Modify: `backend/auth/permissions.py:134`
- Test: `backend/test_patients.py`, `backend/test_permissions.py` (already exist and encode the
  correct expectation)

- [ ] Remove `"patients.delete"` from the `secretary` frozenset in `ROLE_PERMISSIONS`.
- [ ] Run `python -m backend.test_patients` and `python -m backend.test_permissions` — expect
      both to now report ALL PASS.
- [ ] Run the full suite once (`for f in backend/test_*.py ...`) to confirm no regression.
- [ ] Commit: `fix: remove patients.delete permission from secretary role`

---

### Task 2: Enforce payable-amount invariant and add row locking in payments.py

**Files:**
- Modify: `backend/routes/payments.py` (`add_invoice_payment` ~L56-151, `delete_payment`
  ~L154-191)
- Test: add to `backend/test_audit_payments_register.py` (or a new
  `backend/test_payments_integrity.py` if that file is meant to stay focused on audit logs —
  implementer's call; keep it in an existing `test_*.py` so it's picked up by the suite runner)

- [ ] In `add_invoice_payment`, change the invoice fetch to lock the row:
      `db.session.scalar(db.select(Invoice).where(...).with_for_update())`.
- [ ] After computing `new_paid = (invoice.paid_amount or Decimal("0.00")) + amount`, compute
      `payable = invoice.amount - invoice.discount` and, if `new_paid > payable`, return
      `jsonify({"error": "Payment amount exceeds the invoice's remaining payable amount."}), 422`
      **before** adding the `Payment` row or mutating the invoice — mirror the wording/status
      code already used in `backend/routes/invoices.py:111-112` (`_financial_values`) for
      consistency.
- [ ] Apply the same `.with_for_update()` lock to the invoice fetch in `delete_payment`.
- [ ] Reject invalid `payment_method` with `422`/`"Invalid payment method."` instead of silently
      defaulting to `"cash"` (keep the same allow-list `{"cash","card","bank_transfer","other"}`).
- [ ] Reject unparseable `payment_date` with `422`/`"payment_date must be YYYY-MM-DD."` instead of
      silently substituting `date.today()`; a genuinely absent field still defaults to today.
- [ ] Write a test: two sequential payments where the second would push `paid_amount` over
      `payable` → expect `422` and confirm `invoice.paid_amount` is unchanged after the rejected
      call (re-fetch and assert).
- [ ] Write a test: `payment_method: "bogus"` → `422`; `payment_date: "not-a-date"` → `422`.
- [ ] Run the modified test file and the full suite.
- [ ] Commit: `fix: enforce payable-amount invariant, add row locking, reject invalid payment input`

---

### Task 3: Validate waitlist auto-fill doctor_id against clinic

**Files:**
- Modify: `backend/routes/waitlist.py` (`auto_fill_waitlist_entry`, ~L246-316)
- Test: `backend/test_waitlist.py`

- [ ] Before building the `Appointment`, if `data.get("doctor_id")` is provided, validate it
      belongs to `g.current_user.clinic_id` using the same pattern already in
      `create_waitlist_entry` (~L117-128); return `404`/`"Doctor not found."` if not, instead of
      letting an `IntegrityError` bubble up as a 500.
- [ ] Write a test: auto-fill with a `doctor_id` belonging to a different clinic → expect a clean
      `404`, not a 500/unhandled exception.
- [ ] Run `python -m backend.test_waitlist` and the full suite.
- [ ] Commit: `fix: validate cross-clinic doctor_id on waitlist auto-fill`

---

### Task 4: HR shift validation — reject inverted times on update, detect overlaps

**Files:**
- Modify: `backend/routes/hr.py` (`update_shift` ~L210-259; add a shared overlap check used by
  both `create_shift` ~L147-207 and `update_shift`)
- Test: `backend/test_hr.py`

- [ ] After applying any `date`/`start_time`/`end_time` changes in `update_shift`, before
      `log_activity`, validate `shift.start_time < shift.end_time`; return
      `422`/`"start_time must be earlier than end_time."` if not (mirrors `create_shift`'s
      existing check).
- [ ] Add a helper `_shift_overlaps(user_id, shift_date, start_time, end_time, exclude_id=None)`
      that queries `StaffShift` for the same `clinic_id` + `user_id` + `date`, status not
      `cancelled`/`absent`, excluding `exclude_id`, where the time ranges intersect
      (`start_time < end_time_other AND end_time > start_time_other`). Call it from both
      `create_shift` and `update_shift` (after all field validation, before insert/commit);
      return `409`/`"This staff member already has an overlapping shift."` on conflict.
- [ ] While tightening consistency (spec §21/25), change the role gate in `create_shift`,
      `update_shift`, `delete_shift`, `create_credential`, `update_credential`,
      `delete_credential` from `{"head_doctor", "super_admin"}` to `{"head_doctor"}` — super_admin
      has no `clinic_id` and the rest of the app's permission model never grants super_admin
      clinical/staff access; confirm no existing test in `test_hr.py` asserts super_admin access
      before removing it.
- [ ] Write tests: (a) PATCH a shift's `start_time` to after its existing `end_time` → `422`;
      (b) create a shift overlapping an existing one for the same staff member/date → `409`;
      (c) a non-overlapping adjacent shift (end == start) is still allowed.
- [ ] Run `python -m backend.test_hr` and the full suite.
- [ ] Commit: `fix: validate shift time ordering, reject overlapping shifts, tighten HR role gate`

---

### Task 5: Audit logging for admin.py and invoices.py

**Files:**
- Modify: `backend/routes/admin.py` (`create_clinic`, `update_clinic`, `delete_clinic`,
  `purge_clinic_data`, `create_user`, `update_user`, `delete_user`)
- Modify: `backend/routes/invoices.py` (create/update/delete endpoints)
- Test: `backend/test_super_admin.py`, `backend/test_invoices.py`

- [ ] In each admin.py mutation, call `log_activity(action="admin_<verb>_<noun>", ...,
      clinic_id=<the target clinic's id, not the super_admin's None>, resource_type=...,
      resource_id=..., details={...non-secret fields...})` right before `db.session.commit()` —
      e.g. `admin_clinic_created`, `admin_clinic_updated`, `admin_clinic_deleted`,
      `admin_user_created`, `admin_user_updated`, `admin_user_deleted`. Never include password
      hashes or plaintext passwords in `details`.
- [ ] In invoices.py, add `log_activity(action="invoice_created"/"invoice_updated"/
      "invoice_deleted", resource_type="invoice", resource_id=invoice.id, details={...})` before
      each commit, matching the style already used in `payments.py`/`patients.py`.
- [ ] Write a test: as super_admin, create a clinic, then fetch `/api/audit-logs?clinic_id=<new
      clinic id>` (super_admin path) and confirm an `admin_clinic_created` entry with that
      `clinic_id` exists.
- [ ] Write a test: create/update/delete an invoice, then fetch that clinic's audit logs as
      head_doctor and confirm `invoice_created`/`invoice_updated`/`invoice_deleted` entries.
- [ ] Run `python -m backend.test_super_admin`, `python -m backend.test_invoices`, full suite.
- [ ] Commit: `feat: add audit logging for admin and invoice mutations`

---

### Task 6: X-ray metadata length validation

**Files:**
- Modify: `backend/routes/xrays.py` (`_metadata_from_form` and the JSON update path, per the
  audit's line references around L143-148 and L318-320)
- Test: `backend/test_xrays.py`

- [ ] Add explicit length caps before assignment: `tooth_tag`/`type` ≤ 100 chars (matching the
      DB column), `notes` ≤ 2000 chars (a reasonable clinical-note cap — pick a value and apply
      it consistently in both the multipart-upload path and the JSON PATCH path); return
      `422`/`"<field> is too long."` rather than letting it hit the DB.
- [ ] Write a test: PATCH an X-ray with a 5000-char `notes` string → `422`.
- [ ] Run `python -m backend.test_xrays` and the full suite.
- [ ] Commit: `fix: validate X-ray metadata field lengths`

---

### Task 7: Fix trusted-IP handling for rate limiting and audit logs

**Files:**
- Modify: `backend/auth/routes.py` (rate limiter IP extraction), `backend/services/audit.py`
  (same pattern)
- Add: a small shared helper, e.g. `backend/auth/service.py` or a new
  `backend/utils/request_ip.py` — implementer's call on placement, keep it a 5-line function.
- Test: `backend/test_security_and_stress.py`

- [ ] Add `TRUST_PROXY_HEADERS` to `backend/config.py` (default `False`, read from env var of the
      same name).
- [ ] Add `get_client_ip()`: if `current_app.config["TRUST_PROXY_HEADERS"]` is true, use
      `X-Forwarded-For` (first entry) when present, else `request.remote_addr`; if false, always
      use `request.remote_addr`. Use it in both the login/register rate limiter
      (`backend/auth/routes.py`) and `backend/services/audit.py:log_activity`.
- [ ] Document in `.env.example` that `TRUST_PROXY_HEADERS=True` should only be set when deployed
      behind a reverse proxy that itself strips/overwrites client-supplied `X-Forwarded-For`.
- [ ] Write a test: with `TRUST_PROXY_HEADERS` unset/false, sending a distinct
      `X-Forwarded-For` on every login attempt does NOT reset the rate-limit counter (still blocks
      after N attempts, keyed by `remote_addr`).
- [ ] Note in the plan's final report that the in-memory (per-process) rate limiter still won't
      coordinate across multiple gunicorn workers — that's a deployment-topology limitation, not
      something fixable without an external store (Redis), and is out of scope unless the user
      asks for it.
- [ ] Run `python -m backend.test_security_and_stress`, `python -m backend.test_auth`, full suite.
- [ ] Commit: `fix: don't trust X-Forwarded-For unless explicitly behind a proxy`

---

### Task 8: Appointment display names (backend) + status option bug (frontend)

**Files:**
- Modify: `backend/routes/appointments.py` (`_serialize_appointment`, ~L152-167)
- Modify: `web/js/appointments.js` (edit-modal status option ~L376; `mapApiAppointment` ~L3-11)
- Test: `backend/test_appointments.py`

- [ ] In `_serialize_appointment`, join and include `patient_name` (`Patient.name`) and
      `doctor_name` (`User.name`) directly in the response, computed server-side from the
      already-clinic-scoped rows — do not add a new N+1 query per appointment; use the existing
      query's joins or a single batch lookup for the page being serialized.
  - **Note on N+1 avoidance:** the implementer should look at how the list endpoint currently
    fetches appointments for a page and add the patient/doctor name via a join or an `IN (...)`
    batch query keyed by the page's `patient_id`/`doctor_id` values, not a per-row query.
- [ ] In `web/js/appointments.js`, fix the edit-modal `<option value="chair" ...>` to
      `value="in_chair"` (the agenda row's inline `<select>` already does this correctly) — keep
      the `t("chair")` label text if that's the existing translation key for the display label,
      just fix the submitted value.
- [ ] Update `mapApiAppointment` to prefer `item.patient_name`/`item.doctor_name` from the API
      response over the local paginated `state.patients` lookup, falling back to the local lookup
      only if the API didn't send a name (defensive, shouldn't happen once the backend change
      ships).
- [ ] Write a backend test: create an appointment for a patient, fetch the appointments list, and
      assert the response includes the correct `patient_name` (and `doctor_name`).
- [ ] Run `python -m backend.test_appointments`, `node --check web/js/appointments.js`, full
      backend suite.
- [ ] Commit: `fix: include patient/doctor names in appointment responses, fix chair status value`

---

### Task 9: Appointment weekly view pagination (frontend)

**Files:**
- Modify: `web/js/appointments.js` (`loadOnlineAppointments`, ~L46-75)

- [ ] Change `loadOnlineAppointments` to loop: fetch `page=1` with the existing `per_page=100`,
      then if `meta.pages > 1`, fetch the remaining pages (`page=2..meta.pages`) and concatenate
      `data` before assigning to `state.appointments`, reusing the module's existing
      `onlineAppointmentRequest` stale-request-guard token so a patient/week change started mid-
      fetch still discards stale results correctly.
- [ ] Manually sanity-check (read the code path, no live DB fixture needed) that 0/1/many
      appointments still render correctly — 0 and 1 are unchanged (single page, `meta.pages` ≤ 1
      skips the loop).
- [ ] Run `node --check web/js/appointments.js`.
- [ ] Commit: `fix: fetch all pages of weekly appointments instead of truncating at 100`

---

### Task 10: Frontend patient-switch bugs — prescriptions and X-rays go stale

**Files:**
- Modify: `web/js/events.js` (`prescriptionPatientSelect.onchange` ~L172-186,
  `xrayPatientSelect.onchange` ~L193-205)

- [ ] In the prescription patient-select `onchange` handler, call `loadOnlinePrescriptions()`
      (the same function the generic patient-row/`patientRecordSelect` handlers already call)
      after updating `state.selectedPatient`/`state.prescriptionPatientId`, before/instead of the
      bare `render()`.
- [ ] Do the same for the X-ray patient-select `onchange` handler: call `loadOnlineXrays()`.
- [ ] Run `node --check web/js/events.js`.
- [ ] Commit: `fix: reload prescriptions/x-rays when switching patient via their own selectors`

---

### Task 11: Stale-request guard for patient list refresh

**Files:**
- Modify: `web/js/patients.js` (`refreshOnlinePatients`, ~L34-64)

- [ ] Add the same request-counter pattern used elsewhere (e.g.
      `web/js/odontogram.js`'s `onlineOdontogramRequest`): a module-level counter incremented at
      the start of `refreshOnlinePatients`, captured locally, and checked before applying the
      response to `state.patients`/`state.patientTotal`/`state.patientPages`/
      `state.selectedPatient` — discard the response if a newer call has since started.
- [ ] Run `node --check web/js/patients.js`.
- [ ] Commit: `fix: discard stale patient-list responses (pagination/search race)`

---

### Task 12: Documentation accuracy — README/.env.example overclaims

**Files:**
- Modify: `README.md`, `.env.example`

- [ ] Remove or correct the "Pluggable Cloud Storage... via `AERODENT_STORAGE_BACKEND`" claim
      (README.md ~L231) — the S3/R2/MinIO code path in `backend/services/storage.py`'s
      `get_storage()` is never called by any route; `xrays.py` always uses `LocalFileStorage`
      directly. Either (a) wire `xrays.py` to actually call `get_storage()` so the claim becomes
      true, or (b) rewrite the README bullet to describe local-disk storage only and remove the
      cloud-storage claim. **Decision: (b)** — wiring untested cloud storage backends into a
      production-facing README claim is out of scope for this audit pass and risks shipping an
      unverified code path; just make the docs honest.
- [ ] Reconcile the env var name mismatch: README says `AERODENT_STORAGE_BACKEND`, `.env.example`
      says `STORAGE_BACKEND`/`LOCAL_STORAGE_PATH`, actual code reads `AERODENT_STORAGE_PATH`
      (`backend/config.py:40`). Update `.env.example` to use the real variable name
      (`AERODENT_STORAGE_PATH`) and drop the unused `STORAGE_BACKEND`/`LOCAL_STORAGE_PATH`/
      `CORS_ORIGINS` placeholders (confirmed dead — no CORS handling exists; same-origin is
      enforced via Origin/Referer checks).
- [ ] Remove or caveat the Tauri packaging claim (README ~L29,37,110) — no `src-tauri/` project
      exists in the repo; only a `.gitignore` entry for it. State plainly that desktop packaging
      is not currently implemented.
- [ ] Add a one-line note about `TRUST_PROXY_HEADERS` (from Task 7) to `.env.example`.
- [ ] Commit: `docs: correct README/.env.example claims to match actual implementation`

---

### Task 13: Final full-suite verification and report

- [ ] Run the entire backend suite once more against `aerodent_test`, capture full PASS/FAIL.
- [ ] Run `node --check` on every `web/**/*.js` file once more.
- [ ] Write the final report (per the user's spec §53 structure) summarizing what changed, what
      was verified how, and any real remaining limitations (multi-process rate-limiter, no CSP,
      no cloud storage backend, orphaned X-ray file on delete-failure edge case, notes/tooth_tag
      length caps are new but arbitrary-ish values chosen by the implementer).
