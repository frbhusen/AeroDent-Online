# Security in AeroDent Online

The backend is the only authority for authentication and authorization; frontend checks only
hide controls. This document describes the protections and the limits in force.

## Sessions

* The signed, HTTP-only session cookie carries only a user id and a random 256-bit token.
  The token's SHA-256 is stored in `user_sessions`; every request checks that the session
  exists, is not revoked, is within the **idle timeout** (default 120 min,
  `AERODENT_SESSION_IDLE_MINUTES`) and the **absolute lifetime** (default 12 h,
  `AERODENT_SESSION_MAX_HOURS`).
* A new token is issued on every login (no session fixation).
* **Logout revokes the server-side session**, so a copied cookie stops working immediately.
* Changing your password signs out every other device. Deactivating a user, changing their
  password (by a head doctor / admin) or moving them to another clinic revokes all their
  sessions. Deleting a user deletes their sessions (FK cascade).
* Cookie: `HttpOnly`, `SameSite=Strict`, `Path=/`; in production also `Secure` and the
  `__Host-` name prefix. Nothing authentication-related is kept in `localStorage`.
* After logout or session expiry the frontend reloads the document, so no in-memory clinical
  data survives into the next session (see `docs/CACHING.md`).

## Brute-force protection

Counters live in PostgreSQL (`auth_throttles`, keyed by SHA-256 of the subject), so limits hold
across all worker processes. Locks use exponential backoff and are always temporary.

| Scope | Free attempts | Then locked for | Cap | Purpose |
|---|---|---|---|---|
| email + IP | 5 failures / hour | 30 s, doubling | 15 min | one attacker guessing one account |
| email (any IP) | 10 failures / hour | 60 s, doubling | 15 min | attackers rotating IP addresses |
| IP (any email) | 30 failures / hour | 60 s, doubling | 60 min | credential stuffing / username spraying |
| change-password (per user) | 5 wrong current passwords | 60 s, doubling | 30 min | brute force via a stolen session |

* **No lockout of legitimate users:** an IP that successfully signed in to an account within
  the last 30 days is exempt from that account's IP-rotation lock, so a distributed attack
  cannot lock the owner out of their usual device. All locks expire on their own.
* **No account enumeration:** unknown emails are throttled exactly like real ones, receive the
  same `Invalid email or password.` message, and cost the same scrypt verification time.
* Locked requests get `429` with `Retry-After`.
* Failed logins and failed password changes are audit-logged (no passwords).

Other limits: trial-request page intent 30/hour/IP and submissions 5/hour/IP; clinic export
10/hour/user; X-ray uploads 200/hour/user; optional self-registration 5/hour/IP.

## Passwords

* scrypt hashing (Werkzeug). Length 8–128 characters (the maximum bounds hashing cost), not
  blank, not in a common-password list. The same policy applies to login-page changes, staff
  and admin-created accounts, and registration.
* Public self-registration (`/api/auth/register`) is **disabled** unless
  `AERODENT_ALLOW_SELF_REGISTRATION=true`; prospective clinics use the trial-request page.

## Authorization and tenant isolation

* Every object route requires a live session and a role permission, and loads records with
  `WHERE id = :id AND clinic_id = :session_clinic`. Composite `(clinic_id, id)` foreign keys
  make cross-clinic references impossible at the database level.
* `backend/test_idor_sweep.py` exercises **every** object route with another clinic's IDs and
  requires the response to be byte-identical to the response for a non-existent ID.

## Input validation and injection

* All SQL goes through SQLAlchemy with bound parameters; there is no string-built SQL.
* URL IDs are limited to PostgreSQL's integer range; integer query parameters use bounded
  parsing (`backend/services/validation.py`); enum fields require strings; text fields are
  length-checked against their columns; JSON bodies must be objects.
* `backend/test_security_fuzz.py` sends ~10,000 hostile requests (huge/negative numbers, SQL
  and HTML payloads, wrong types, over-long text, malformed JSON, fake uploads) to every route,
  including with real record IDs, and fails on any 5xx, leaked internals, or a value that
  reached the database unvalidated.
* Output: every user-supplied value rendered into HTML goes through `esc()`.

## HTTP headers

* `Content-Security-Policy`: `script-src 'self'` (no inline scripts or inline event handlers
  exist), `object-src 'none'`, `frame-ancestors 'none'`, `base-uri 'self'`, `form-action 'self'`.
  X-ray files use an even stricter sandboxing policy.
* `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`,
  `Cross-Origin-Opener-Policy` / `Cross-Origin-Resource-Policy: same-origin`, restrictive
  `Permissions-Policy`, `Strict-Transport-Security` in production, `X-XSS-Protection: 0`.
* API responses: `Cache-Control: no-store, private` (see `docs/CACHING.md`).
* CSRF: state-changing API requests with a foreign `Origin`/`Referer` are rejected, the session
  cookie is `SameSite=Strict`, and JSON endpoints ignore non-JSON bodies. No CORS is enabled.

## Errors, secrets, logging

* Clients only ever see generic messages for server faults; no stack traces, SQL, or paths.
  The Werkzeug debugger only runs when `AERODENT_ENV=development`.
* `SECRET_KEY` must be set (≥ 32 characters) in production; database and storage credentials
  come from environment variables. No secret is returned by any endpoint.
* Audit logs record security events (logins, failures, lockouts, password changes, uploads,
  downloads, exports, deletions) without passwords, session tokens, or clinical content, and
  are written in a savepoint so an audit failure never breaks the real operation.

## Known limitations

* Brute-force limits are keyed by client IP; behind a reverse proxy set
  `TRUST_PROXY_HEADERS=True` only if the proxy overwrites `X-Forwarded-For`.
* `style-src` still allows inline styles because templates use `style=""` attributes.
* A determined attacker controlling many IPs can still delay (not block) logins for an
  account from devices that never signed in to it before — capped at 15 minutes.
