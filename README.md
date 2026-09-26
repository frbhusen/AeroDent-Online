# AeroDent & AeroDent Online

A modern dental clinic management system supporting both a multi-tenant cloud-hosted **Online Mode** and a standalone, local-first **Offline Mode**.

---

## 1. System Architecture

AeroDent supports two distinct, isolated operating modes:

### Online Mode (Multi-Tenant Cloud)

```text
Frontend (Vanilla JS / Browser)
    ↓  (HTTP with credentials: "include")
Flask REST API (Application Server)
    ↓  (SQLAlchemy ORM + PostgreSQL)
PostgreSQL Database + Protected Local File Storage (X-rays)
```

- **Authentication**: Server-side HTTP-only session cookies (`/api/auth/login`, `/api/auth/me`, `/api/auth/logout`).
- **Authorization**: Centralized role-based access control matrix (`head_doctor`, `doctor`, `secretary`).
- **Multi-Tenancy**: Strict clinic-level data isolation enforced via foreign keys and composite constraints (`clinic_id`), parameterized SQLAlchemy queries, and 404 responses for cross-tenant resource lookups.
- **X-Ray Storage**: Secure filesystem storage outside web roots, streaming image bytes through authenticated, clinic-scoped endpoints (`/api/x-rays/<id>/file`).

### Offline Mode (Local-First PWA)

```text
Browser
    ↓
IndexedDB + Web Crypto API (PBKDF2 Local PIN Auth)
```

- Zero backend dependency.
- Stores clinical records directly in the browser's IndexedDB.
- Protected by local PIN with PBKDF2 hashing and automatic inactivity timeout lock.
- Supports Excel/HTML backups.
- **Not currently implemented**: a native desktop wrapper (e.g. Tauri). Offline mode today
  runs as a browser-based PWA only; there is no `src-tauri/` project or packaging step in
  this repository.

### Android App

```text
Android WebView shell (mobile/android)
    ↓ HTTPS, same HttpOnly session cookie as the browser
Online platform (Flask + PostgreSQL)
```

A lightweight app that hosts the online platform; the backend stays on the server. Build it with
`cd mobile/android && ./gradlew assembleRelease -PaerodentServerUrl=https://your-server`. See
[docs/MOBILE.md](docs/MOBILE.md).

*Critical Mode Principle*: Online mode never falls back to IndexedDB on network failures, and offline mode never contacts the API without explicit mode selection (`?mode=online`).

---

## 2. Roles & Permissions (Online)

| Module / Action | Head Doctor | Doctor | Secretary |
| :--- | :---: | :---: | :---: |
| **Dashboard** | Read | Read | Read |
| **Patients** | Read, Create, Update, Delete | Read, Create, Update, Delete | Read, Create, Update (Admin fields only) |
| **Odontogram** | Read, Update, Delete | Read, Update, Delete | Read-only |
| **Treatments** | Read, Create, Update, Delete | Read, Create, Update, Delete | Read-only |
| **Treatment Plans** | Read, Create, Update, Delete | Read, Create, Update, Delete | Read-only |
| **Appointments** | Full CRUD | Full CRUD | Full CRUD |
| **Prescriptions** | Read, Create, Update, Delete | Read, Create, Update, Delete | Read-only |
| **X-Rays** | Read, Upload, Update, Delete | Read, Upload, Update, Delete | Read & Download only |
| **Invoices** | Read, Create, Update, Delete | Read, Create, Update | Read, Create, Update |
| **Inventory** | Full management (items, categories, suppliers, receive, use, adjust, write-off) | Read, Receive, Use/Return | Read, Receive, Use/Return, Manage suppliers |
| **Clinic Settings** | Read, Update | Read-only | No access |
| **Staff Management** | Full CRUD | No access | No access |
| **Clinic Export** | Full export | Full export | No access |

---

## 3. Directory Layout

```text
.
├── backend/                  # Flask REST API
│   ├── auth/                 # Session auth, login/logout, RBAC permissions
│   ├── models/               # SQLAlchemy models (Clinic, User, Patient, etc.)
│   ├── routes/               # API route blueprints (patients, treatments, etc.)
│   ├── services/             # Audit log, X-ray storage, inventory stock operations
│   ├── app.py                # Flask app factory and entry point
│   ├── config.py             # Development, testing, production configurations
│   ├── requirements.txt      # Python dependencies
│   ├── seed.py               # Database seeder for demo clinics and accounts
│   └── test_*.py             # Automated backend & integration test suites
├── migrations/               # Alembic database migrations
├── mobile/android/           # Android app: WebView shell around the online platform (docs/MOBILE.md)
├── docs/                     # Security, caching, X-ray storage and mobile documentation
├── web/                      # Vanilla JS frontend application
│   ├── index.html            # Main application shell
│   ├── styles.css            # Responsive styles (LTR & RTL supported)
│   ├── i18n.js               # Localization dictionary (English & Arabic)
│   ├── sw.js                 # PWA Service Worker (skips /api/ calls)
│   ├── db.js                 # Offline IndexedDB persistence engine
│   └── js/                   # Frontend modules
│       ├── api.js            # Central API client (credentials: include)
│       ├── state.js          # Shared state manager
│       ├── core.js           # Utilities & helpers
│       ├── ui.js             # View rendering, navigation, and modals
│       ├── nativeBridge.js   # Android app integration (downloads, print, Back); inert in browsers
│       ├── auth.js           # Session auth & permission helpers
│       ├── patients.js       # Patient management
│       ├── odontogram.js     # Dental odontogram (FDI / Universal)
│       ├── treatments.js     # Treatments & Invoices
│       ├── treatmentPlans.js # Treatment planning
│       ├── appointments.js   # Calendar & appointment scheduling
│       ├── prescriptions.js  # Medications & prescription generator
│       ├── xrays.js          # Secure X-ray viewer & uploader
│       ├── timeline.js       # Patient clinical history timeline
│       ├── inventory.js      # Inventory: stock, batches/expiry, suppliers, categories
│       ├── backup.js         # Offline export/import & online clinic data export
│       ├── events.js         # Event listeners & UI dispatchers
│       └── app.js            # App initialization, dashboard, settings & staff
```

---

## 4. Setup & Running Locally

### Prerequisites

- Python 3.11+
- PostgreSQL database
- Node.js (optional; only used to run `node --check` for frontend JS syntax validation, see
  the Testing section below — there is no frontend build step or bundler)

### 1. Environment Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Set your database credentials and secret key in `.env`:

```ini
DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/aerodent
AERODENT_ENV=development
SECRET_KEY=generate-a-secure-random-secret-key-32-chars-minimum
AERODENT_STORAGE_PATH=storage
```

The session cookie's `Secure` flag is enabled automatically whenever `AERODENT_ENV=production`;
it is not independently configurable via an environment variable.

### 2. Backend Installation & Database Setup

Activate your Python virtual environment and install requirements:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
```

Run database migrations:

```powershell
flask --app backend.app db upgrade
```

Seed initial clinics and demo accounts:

```powershell
python -m backend.seed
```

Default demo accounts created by seed:

| Scope | Role | Email | Password |
| :--- | :--- | :--- | :--- |
| **Platform-Wide** | **Super Admin** | `admin@aerodent.local` | `SuperAdminPassword123!` |
| Clinic #1 | Head Doctor | `head@aerodent.local` | `DoctorPassword123!` |
| Clinic #1 | Doctor | `doctor@aerodent.local` | `DoctorPassword123!` |
| Clinic #1 | Secretary | `secretary@aerodent.local` | `DoctorPassword123!` |

### 3. Starting the Unified Server (Web App + REST API)

```powershell
python -m flask --app backend.app run --port 5000
```

### 4. Running the Frontend

Serve the `web/` folder through a local HTTP server:

```powershell
python -m http.server 5500 --directory web
```

Then navigate to:

- **Online Mode**: `http://localhost:5500/?mode=online`
- **Offline Mode**: `http://localhost:5500/?mode=offline`

---

## 5. Running Tests

Run all unit and tenant isolation test suites:

```powershell
Get-ChildItem -Path backend -Filter "test_*.py" | ForEach-Object {
    Write-Host "=== Running $($_.Name) ==="
    .\.venv\Scripts\python.exe -m "backend.$($_.BaseName)"
}
```

Validate JavaScript syntax:

```powershell
Get-ChildItem -Path web -Recurse -Filter "*.js" | ForEach-Object {
    node --check $_.FullName
}
```

---

## 6. Inventory Module (Online)

Clinic-scoped stock management for dental materials, medicines, consumables, instruments and
supplies (`/api/inventory/...`, `web/js/inventory.js`). Offline mode does not include inventory.

- **Server-authoritative stock**: an item's `quantity` is never edited directly. Every change is an
  append-only `inventory_movements` row (`opening`, `stock_in`, `usage`, `return`, `adjustment`,
  `expired`, `damaged`, `loss`, `supplier_return`) that records the signed change, the resulting
  balance, who made it, and why. Mistakes are corrected with a new adjustment, never by rewriting
  history. Stock operations lock the item row and run in a single transaction.
- **No negative stock**: usage or write-offs larger than the available quantity are rejected with
  `409`; database check constraints back this up.
- **Batches & expiry (optional per item)**: items with *batch tracking* hold stock in lots with
  batch numbers and expiry dates. Usage consumes earliest-expiry-first automatically (or from a
  chosen lot). Expired lots are excluded from usable stock and cannot be used; they stay on hand
  until written off, so history is preserved. The "expiring soon" window is a clinic setting
  (`inventory_expiry_warning_days`, default 60).
- **Stock status**: `out` when usable quantity ≤ 0, `low` when ≤ the item's own minimum.
- **Estimated value**: usable quantity × recorded unit cost (lot cost where known, otherwise the
  item's latest received cost). It is an operational estimate, not an accounting valuation.
- **Clinical links**: a movement may carry `reference_type`/`reference_id` (patient, treatment,
  appointment), validated against the same clinic but intentionally not a foreign key.
- **Deletion policy**: items are deactivated, never deleted. Categories and suppliers can only
  be deleted when nothing references them; otherwise they are deactivated.
- **Permissions**: `inventory.read`, `inventory.create`, `inventory.update`, `inventory.delete`
  (deactivate), `inventory.stock_in`, `inventory.stock_out` (usage/return), `inventory.adjust`
  (count corrections and write-offs), `inventory.manage_categories`, `inventory.manage_suppliers`.
- All inventory actions are written to the audit log (`inventory_*` actions).

---

## 7. Super Admin & Subscription System Architecture

The **Super Admin** role (`super_admin`) is the global platform owner who controls clinic subscriptions, clinic access, and all staff accounts:

- **Custom Admin Portal**: Dedicated dashboard for subscriptions, metrics, clinics, and global user management. No access to clinical data (patients, treatments, odontograms, etc.), preserving clinic privacy and HIPAA compliance.
- **Deactivation Cascade Rule**: If a clinic's Head Doctor is deactivated, or the clinic's subscription expires/is suspended, the **entire clinic** is locked out from signing in and accessing active sessions. Other clinics and other head doctors remain completely unaffected.
- **Staff Role Safeguards**: Head doctors are strictly prohibited from creating or promoting other users to `head_doctor`. Only the platform Super Admin can assign or create head doctors.
- **Dedicated Admin API**: `/api/admin/metrics`, `/api/admin/clinics`, `/api/admin/users`.

---

## 8. Production Deployment Readiness

- Ensure `AERODENT_ENV=production` — this automatically enforces HTTPS-only (`Secure`) session
  cookies; there is no separate `SESSION_COOKIE_SECURE` environment variable to set.
- Deploy Flask behind a production WSGI server (such as Gunicorn or Waitress) behind Nginx reverse proxy.
- If deployed behind a reverse proxy, set `TRUST_PROXY_HEADERS=True` only once that proxy is
  configured to strip/overwrite any client-supplied `X-Forwarded-For` header, otherwise leave
  it `False` (the default) so the login/registration rate limiter cannot be bypassed by a
  spoofed header.
- Set `SECRET_KEY` to a random value of at least 32 characters (enforced in production).
- Run `flask --app backend.app db upgrade` on every deploy. X-ray images are stored in
  PostgreSQL (`xray_images`), so a normal database backup covers them. Deployments that still
  have X-rays from the old file storage can import them once with
  `flask --app backend.app xrays import-legacy` (see [docs/XRAY_STORAGE.md](docs/XRAY_STORAGE.md)).
- Protect database connection strings and secret keys using environment secrets.
- Login throttling, rate limits and sessions are stored in PostgreSQL, so they hold across all
  worker processes and instances without an extra store.
- Optional settings: `AERODENT_SESSION_IDLE_MINUTES` (default 120),
  `AERODENT_SESSION_MAX_HOURS` (default 12), `AERODENT_ALLOW_SELF_REGISTRATION` (default
  `false`), `AERODENT_XRAY_MAX_MB` (default 25).

Further documentation:

- [docs/SECURITY.md](docs/SECURITY.md): authentication, sessions, brute-force limits, headers.
- [docs/CACHING.md](docs/CACHING.md): what is cached where, and why clinic data never is.
- [docs/XRAY_STORAGE.md](docs/XRAY_STORAGE.md): lossless, integrity-checked X-ray storage.
- [docs/MOBILE.md](docs/MOBILE.md): the Android app.

---

## 9. Commercial SaaS Capabilities

- **Audit Trail & Activity Logging**: Tamper-evident logging tracking all patient modifications, invoices, logins, and registrations (`/api/audit-logs`), viewable by Head Doctors and Super Admins.
- **Invoice Installments & Debt Ledger**: Full support for partial down-payments and installments with automatic balance recalculation (`POST /api/invoices/<id>/payments`).
- **Clinical Flow & Scheduler Statuses**: Real-time appointment status progression (`booked`, `arrived`, `in_chair`, `completed`, `cancelled`) with instant calendar dropdowns.
- **Spotlight Command Palette (`Ctrl + K`)**: High-speed patient lookup by name, phone, or chart ID, with keyboard navigation and quick action execution.
- **Self-Service Trial Onboarding**: 14-day free trial self-registration (`POST /api/auth/register`) with automatic clinic and head doctor account provisioning.
- **X-Ray File Storage**: Private, authenticated local-disk storage outside the web root
  (`AERODENT_STORAGE_PATH`), served only through clinic-scoped API endpoints. There is currently
  no pluggable cloud storage backend (S3, R2, MinIO) wired into the upload/download routes.