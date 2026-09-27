# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

AeroDent is a dental clinic management system with two independent, isolated modes selected by
URL query param (`?mode=online` / `?mode=offline`):

- **Online**: multi-tenant Flask REST API + PostgreSQL, session-cookie auth, RBAC (`head_doctor`,
  `doctor`, `secretary`, plus a platform-wide `super_admin`).
- **Offline**: local-first PWA, zero backend — everything lives in the browser's IndexedDB
  (`web/db.js`), PIN-protected with PBKDF2. Never contacts the API.

*Critical Mode Principle*: online mode never falls back to IndexedDB on network failure, and
offline mode never contacts the API. Any frontend code path is one or the other, gated by
`window.AERODENT_ONLINE` — don't write logic that silently crosses that boundary.

There's also `mobile/android`: a thin WebView shell around the same online platform (no separate
backend). See `docs/MOBILE.md`.

Read `README.md` first for the full roles/permissions matrix, directory layout, inventory module
semantics, and super-admin/subscription architecture — it's kept accurate and this file doesn't
repeat it.

## Commands

No build step, no bundler, no package.json/npm for the frontend — plain `<script>` tags loaded
in a specific order from `web/index.html`. If you add a new `web/js/*.js` file, add its `<script>`
tag there too, positioned before `events.js`/`app.js` (which wire up handlers and expect
everything else already defined).

Backend setup:
```bash
pip install -r backend/requirements.txt
flask --app backend.app db upgrade      # run Alembic migrations
python -m backend.seed                  # demo clinics/accounts (dev only, never in prod)
python -m flask --app backend.app run --port 5000
```

Serve the frontend separately in dev (the Flask app also serves `web/` directly, but a plain
static server works too):
```bash
python -m http.server 5500 --directory web
```

### Tests

Backend tests are plain scripts (no pytest), one file per feature area under `backend/test_*.py`.
Each is runnable standalone and prints `PASS:` lines / raises `AssertionError` on failure:
```bash
python -m backend.test_patients
python -m backend.test_appointments
```
Run all of them:
```bash
for f in backend/test_*.py; do python -m "backend.$(basename "$f" .py)" || break; done
```
There's no per-test-function runner — to isolate one case, temporarily call just that function
from the file's `if __name__ == "__main__":` block, or invoke it directly with `python -c`.

Frontend has no test suite; syntax-check any changed JS file:
```bash
node --check web/js/appointments.js
```

### Migrations

```bash
flask --app backend.app db migrate -m "description"
flask --app backend.app db upgrade
```
Model changes go in `backend/models/*.py`; always generate a migration for schema changes rather
than hand-editing the DB.

## Backend architecture (`backend/`)

- `app.py` — Flask app factory (`create_app`). Registers every blueprint, global CSRF check
  (Origin/Referer match on state-changing `/api/*` requests — there is **no CORS support by
  design**, frontend is same-origin), security headers, and JSON error handlers (404/etc. never
  return HTML for `/api/*` paths, but do serve the SPA shell for non-API 404s so client-side
  routing works).
- `auth/` — `routes.py` (login/logout/me, session cookie only stores `user_id`), `permissions.py`
  (`ROLE_PERMISSIONS` dict mapping role → permission strings, `require_permission("x.read")`
  decorator, `validate_patient_update` for field-level admin/clinical split), `service.py`
  (password hashing).
- `models/` — one SQLAlchemy model file per entity, all exported from `models/__init__.py`.
  Every clinic-scoped table has a `clinic_id` FK.
- `routes/` — one blueprint per resource, mounted under `/api/<resource>`. **The standard pattern
  in every route handler**: `@login_required` (or `@require_permission("resource.action")`) sets
  `g.current_user` / `g.current_clinic`; every query then filters
  `Model.clinic_id == g.current_user.clinic_id`. Cross-tenant lookups return 404, never 403 (don't
  leak whether a resource exists in another clinic). Follow this pattern exactly for any new
  route — it's how multi-tenant isolation is enforced, there's no ORM-level global filter doing
  it for you.
- `services/` — cross-cutting logic: `audit.py` (`log_activity`, write to every mutating action),
  inventory stock movements, X-ray storage, clinic backup/export.
- CLI commands (`admin_cli`, `xrays_cli`) are registered in `app.py` and live in `backend/cli.py`
  — e.g. `flask --app backend.app admin create-super-admin`, `flask --app backend.app xrays
  import-legacy`.

## Frontend architecture (`web/`)

No framework, no virtual DOM, no modules — every `web/js/*.js` file defines plain functions in
global scope, loaded via ordered `<script>` tags (see `web/index.html`). Key pieces:

- `state.js` — one global `state` object holding all UI state (pagination, loading/error flags,
  selected records, current view, etc.).
- `ui.js` — `render()` is the entire rendering strategy: it sets `#view`'s `innerHTML` to the
  output of whichever `render<Feature>()` function matches `state.view`, then calls `bindView()`
  to re-attach event handlers. **There is no diffing** — every state change that should be
  reflected on screen calls `render()`, which regenerates the whole current view's HTML string
  from scratch. Feature modules (`patients.js`, `appointments.js`, etc.) each export a
  `render<Feature>()` returning an HTML template string, and `events.js` defines the matching
  `bind<Feature>Events()` wireup.
- `api.js` — single `apiRequest`/`ApiError` wrapper around `fetch`, always `credentials:
  "include"`, same-origin base URL only (never derived from the page URL, to avoid leaking
  credentials to a crafted host).
- `db.js` — IndexedDB layer for offline mode (`dbGetAll`, `dbPut`, `dbDelete`); mirrors the shape
  of the online API's data so feature modules can branch on `window.AERODENT_ONLINE` and use
  whichever backing store applies.
- `events.js` — all DOM event delegation/binding; `app.js` — app bootstrap, dashboard, settings,
  staff.
- `i18n.js` — English/Arabic dictionary, `t(key)` helper; the UI supports both LTR and RTL
  (`styles.css` uses logical properties like `margin-inline-start`/`border-inline-start`, not
  `left`/`right` — keep using logical properties in new CSS).

When adding a feature, the usual shape is: a `web/js/<feature>.js` with `render<Feature>()` +
data-loading functions, a matching `bind<Feature>Events()` in `events.js`, state fields added to
`state.js`, and (for online mode) a Flask blueprint in `backend/routes/` following the
`g.current_user.clinic_id` scoping pattern above.
