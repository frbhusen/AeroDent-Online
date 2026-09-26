# Caching in AeroDent Online

Guiding rule: **correctness and privacy beat speed.** Anything that contains clinic or
patient data, or that depends on who is signed in, is never cached anywhere. Caching is used
only for the public application shell, where it gives a large, measurable benefit.

## What is cached

| What | Where | Lifetime | Invalidation |
|---|---|---|---|
| JS / CSS / i18n / icons / manifest requested with `?v=<asset-version>` | Browser HTTP cache | `public, max-age=31536000, immutable` | The asset version is a SHA-256 of every file in `web/`. Any deploy that changes a file changes the version, so `index.html` references new URLs. |
| Same files requested **without** `?v=` | Browser HTTP cache | `no-cache` (always revalidated) | ETag / Last-Modified → `304 Not Modified` when unchanged. |
| Gzip-compressed copies of text assets | Server process memory (`StaticAssets._gzip_cache`) | Process lifetime | Keyed by `(path, mtime, size)`; a changed file is recompressed. The version itself is computed at process start, so deploys restart workers as usual. |
| Application shell (index + versioned assets) | Service worker Cache API, cache name `aerodent-shell-<version>` | Until the next version | Old caches are deleted when a new service worker activates. |

Measured effect on a cold load of the shell: `styles.css` 82.7 KB → 15.4 KB (gzip),
all JS/CSS ≈ 680 KB → ≈ 140 KB; repeat visits load the shell from cache with no network
round trip for versioned assets.

## What is never cached

* **Every `/api/` response** is sent with `Cache-Control: no-store, private`,
  `Pragma: no-cache`, `Expires: 0`, and `Vary: Cookie`. This covers patients, treatments,
  prescriptions, appointments, invoices, payments, inventory, audit logs, settings, and X-ray
  image bytes (`/api/x-rays/<id>/file`). Because nothing is stored, there is nothing to
  invalidate on create/update/delete: every read goes to PostgreSQL and is authorized by the
  current session.
* The service worker explicitly ignores `/api/` and never stores a response marked `private`.
* `index.html` is `no-store`. It holds no data itself, but it is the document that holds
  private data **in memory** once signed in; `no-store` stops browsers from restoring a
  signed-in page from the back/forward cache after logout.
* No server-side cache of clinical data is used. The per-request cost of reading from
  PostgreSQL is small for a clinic, and a shared cache would add a cross-tenant leakage and
  staleness risk (e.g. a deactivated user or a permission change must take effect
  immediately). This was a deliberate decision, not an omission.

## Logout, account switching, permission changes

* **Logout** revokes the server-side session (see `docs/SECURITY.md`) and then reloads the
  document. All in-memory state (patients, dashboard, staff, inventory, permissions) is
  discarded with the old document, so the next user cannot see any of it.
* **Session expiry / revocation**: the first `401` from the API triggers the same reload and
  shows "Your session has ended".
* **Permission / role / clinic changes** are enforced by the server on every request (roles are
  re-read from the database for each request). The frontend's permission checks only hide
  buttons; after the next page load they reflect the new role.
* Nothing authentication-related is kept in `localStorage`/`sessionStorage`; the only
  `sessionStorage` key (`aerodent-auth-notice`) holds the words `signedOut`/`sessionExpired`.

## Offline mode

Offline mode (`?mode=offline`) keeps its data in IndexedDB on the device, as before. The
service worker only provides the cached shell so the app can open without a network.
