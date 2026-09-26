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

### Offline Mode (Local-First Desktop/PWA)

```text
Browser / Tauri Desktop Wrapper
    ↓
IndexedDB + Web Crypto API (PBKDF2 Local PIN Auth)
```

- Zero backend dependency.
- Stores clinical records directly in the browser's IndexedDB.
- Protected by local PIN with PBKDF2 hashing and automatic inactivity timeout lock.
- Supports Excel/HTML backups and Tauri Windows packaging.

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
│   ├── services/             # Storage service (X-ray file handling)
│   ├── app.py                # Flask app factory and entry point
│   ├── config.py             # Development, testing, production configurations
│   ├── requirements.txt      # Python dependencies
│   ├── seed.py               # Database seeder for demo clinics and accounts
│   └── test_*.py             # Automated backend & integration test suites
├── migrations/               # Alembic database migrations
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
│       ├── auth.js           # Session auth & permission helpers
│       ├── patients.js       # Patient management
│       ├── odontogram.js     # Dental odontogram (FDI / Universal)
│       ├── treatments.js     # Treatments & Invoices
│       ├── treatmentPlans.js # Treatment planning
│       ├── appointments.js   # Calendar & appointment scheduling
│       ├── prescriptions.js  # Medications & prescription generator
│       ├── xrays.js          # Secure X-ray viewer & uploader
│       ├── timeline.js       # Patient clinical history timeline
│       ├── backup.js         # Offline export/import & online clinic data export
│       ├── events.js         # Event listeners & UI dispatchers
│       └── app.js            # App initialization, dashboard, settings & staff
```

---

## 4. Setup & Running Locally

### Prerequisites

- Python 3.11+
- PostgreSQL database
- Node.js (for Tauri desktop packaging or PWA tooling)

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
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=storage/xrays
SESSION_COOKIE_SECURE=False
```

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

## 6. Super Admin & Subscription System Architecture

The **Super Admin** role (`super_admin`) is the global platform owner who controls clinic subscriptions, clinic access, and all staff accounts:

- **Custom Admin Portal**: Dedicated dashboard for subscriptions, metrics, clinics, and global user management. No access to clinical data (patients, treatments, odontograms, etc.), preserving clinic privacy and HIPAA compliance.
- **Deactivation Cascade Rule**: If a clinic's Head Doctor is deactivated, or the clinic's subscription expires/is suspended, the **entire clinic** is locked out from signing in and accessing active sessions. Other clinics and other head doctors remain completely unaffected.
- **Staff Role Safeguards**: Head doctors are strictly prohibited from creating or promoting other users to `head_doctor`. Only the platform Super Admin can assign or create head doctors.
- **Dedicated Admin API**: `/api/admin/metrics`, `/api/admin/clinics`, `/api/admin/users`.

---

## 7. Production Deployment Readiness

- Ensure `AERODENT_ENV=production`.
- Set `SESSION_COOKIE_SECURE=True` to enforce HTTPS cookies.
- Deploy Flask behind a production WSGI server (such as Gunicorn or Waitress) behind Nginx reverse proxy.
- Ensure the `storage/xrays` directory has appropriate read/write permissions for the application user and is backed up regularly.
- Protect database connection strings and secret keys using environment secrets.

---

## 8. Commercial SaaS Capabilities

- **Audit Trail & Activity Logging**: Tamper-evident logging tracking all patient modifications, invoices, logins, and registrations (`/api/audit-logs`), viewable by Head Doctors and Super Admins.
- **Invoice Installments & Debt Ledger**: Full support for partial down-payments and installments with automatic balance recalculation (`POST /api/invoices/<id>/payments`).
- **Clinical Flow & Scheduler Statuses**: Real-time appointment status progression (`booked`, `arrived`, `in_chair`, `completed`, `cancelled`) with instant calendar dropdowns.
- **Spotlight Command Palette (`Ctrl + K`)**: High-speed patient lookup by name, phone, or chart ID, with keyboard navigation and quick action execution.
- **Self-Service Trial Onboarding**: 14-day free trial self-registration (`POST /api/auth/register`) with automatic clinic and head doctor account provisioning.
- **Pluggable Cloud Storage**: Out-of-the-box support for AWS S3, Cloudflare R2, MinIO, or local disk via `AERODENT_STORAGE_BACKEND`.