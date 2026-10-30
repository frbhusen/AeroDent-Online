# AeroDent standalone (desktop) edition

The same clinic screens as the head-doctor panel of the online edition, running entirely on one
computer: a local backend (127.0.0.1 only) with all data in a single SQLite file, opened in its own
window. No internet, no accounts for other people, no platform administration, no trial sign-up and
no landing page. The online edition is untouched.

## Run it (development)

```bash
python -m standalone.launcher                 # opens the app window (Edge/Chrome --app mode)
python -m standalone.launcher --no-window     # only the local server (open http://127.0.0.1:48731)
python -m standalone.launcher --check         # start, verify it answers, exit
python -m standalone.launcher --data-dir D:\AeroDentTest   # use a different data folder
```

## Build the Windows program

```bash
pip install -r standalone/requirements.txt     # Nuitka (needs a C compiler: Visual Studio Build Tools) 
python -m standalone.build --zip               # dist/AeroDent/AeroDent.exe and dist/AeroDent-windows.zip
```

Needs Node.js too (the build runs `npm install` in `standalone/tools` for the JavaScript obfuscator).
The first build takes a long time (the whole backend is compiled to native code); later builds are faster.

Unzip anywhere and double-click `AeroDent.exe`. The first start shows the setup screen (clinic name,
doctor name, sign-in email, password, country, currency).

### What the installed program contains

* **Python (backend + launcher):** compiled to native machine code by Nuitka. No `.py` or `.pyc` files are shipped.
* **Frontend:** the scripts are obfuscated (local names and strings scrambled, the global function names
  that scripts call each other by are kept), then all web files are packed into one scrambled blob that is
  compiled into the program and served from memory. There is no `web` folder on disk.
* **Not included:** the tests, the landing page, the trial page.

This removes the source code and makes reverse engineering slow and impractical for most people. It cannot
make a program that runs on someone's computer impossible to inspect: the browser window must receive the
frontend scripts to run them (so a determined person can read the obfuscated scripts with the developer
tools), and native code can still be disassembled. Treat it as protection against copying the source, not
as a security boundary; keep real secrets and rules on the server side (the online edition) if that matters.

## Where the data lives

`%APPDATA%\AeroDent` (override with `AERODENT_DATA_DIR` or `--data-dir`):

| File | Purpose |
|------|---------|
| `aerodent.db` | the clinic database (SQLite) |
| `backups\aerodent-YYYYMMDD.db` | an automatic copy once per day, the last 14 are kept |
| `secret.key` | signs the sign-in session; keep it with the database |
| `window-profile\` | the app window's own settings (language...) |
| `aerodent.log` | server log |

Moving to another computer: copy the whole folder, or use Settings → Backup (export/import) inside the app.

## How it differs from the online edition

* `AERODENT_EDITION=standalone` (set by the launcher) removes `/api/admin/*` and the trial endpoints,
  adds `/api/setup/*` (first run only) and serves the app at `/`.
* The schema is created from the models and upgraded additively (new tables, new nullable columns) by
  `standalone/schema.py`; the Alembic migrations are PostgreSQL-specific and are not used.
* Staff accounts, active sessions and seat limits are hidden; the single head doctor manages everything.
* The old browser-only offline mode (`?mode=offline`, IndexedDB) still exists unchanged.
* `standalone/_frontend_blob.py` is generated during the build and deleted afterwards; never commit it.

## Tests

`python -m backend.test_standalone` covers setup, the removed routes and the main workflows on SQLite.
Any other test can run on SQLite too: set `DATABASE_URL=sqlite:///path/test.db` and create the tables
first (`db.create_all()`). Two tests are PostgreSQL-only by design: the inventory concurrency stress
test and `test_xray_storage` (it corrupts bytes with a PostgreSQL function).
