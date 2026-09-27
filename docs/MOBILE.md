# AeroDent for Android

The Android app (`mobile/android`) is a thin, locked-down WebView shell around the AeroDent web
platform. The server stays the single source of truth: every page, API call, permission check
and piece of clinic data lives on the AeroDent server. The app adds only what a browser tab
would otherwise provide on a phone.

## Architecture

```
┌──────────────────────── Android app (com.aerodent.app) ────────────────────────┐
│ MainActivity                                                                   │
│  └─ WebView ── loads https://<your server>/?mode=online (the normal web app)  │
│       ├─ ShellClient      only the configured server origin loads in-app;      │
│       │                   other links open in the system browser; TLS errors   │
│       │                   are never bypassed; no connection → offline screen   │
│       ├─ FileChooser      <input type=file>: files/gallery + "take a photo"    │
│       ├─ DownloadListener server downloads (X-ray originals) → Downloads/AeroDent │
│       └─ NativeChannel    `window.AeroDentNative`, injected ONLY into pages    │
│                           from the server origin: save generated files, print │
│ assets/offline/          "No connection" page (uses web/i18n.js, EN/AR)        │
└────────────────────────────────────────────────────────────────────────────────┘
                                   │ HTTPS only (release)
                                   ▼
                    AeroDent server (Flask + PostgreSQL), unchanged
```

### Why a native WebView shell (and not Capacitor, React Native, or a rewrite)

* **The backend stays on the server.** The app renders the same web UI the browser does, so
  every security control (server-side sessions, RBAC, clinic isolation, rate limits, CSP) applies
  unchanged. There is no second API client and no business logic in the app.
* **Nothing to keep in sync.** A web deploy updates the app immediately. A new APK is needed only
  when the shell itself changes.
* **HttpOnly sessions keep working.** The WebView loads the server origin directly, so the session
  cookie (`HttpOnly`, `Secure`, `SameSite=Strict`, `__Host-` prefix in production) is handled
  by the WebView's cookie store exactly as in a browser. JavaScript, including the app's
  own, can never read it. The app stores no credentials or tokens.
* **The strict CSP stays intact.** Capacitor's remote-URL mode routes page loads through its
  own proxy and injects inline scripts, which the platform's `script-src 'self'` policy would
  block (and weakening it would lower security for every user). A plain WebView needs neither.
* **Small and auditable.** Four Java classes, no third-party SDKs beyond AndroidX, a ~420 KB
  release APK.

## What the shell handles

| Concern | How |
|---|---|
| Sessions | WebView cookie store; flushed to disk on pause. Server-side logout/expiry works as on the web (the page clears itself and returns to sign-in). |
| Navigation scope | Only URLs whose scheme, host and port match the configured server load in the WebView. Everything else (e-mail links, external sites) opens in the system browser. |
| No connection / server unreachable | A bundled page (`assets/offline/offline.html`) in the user's language, with a *Try again* button. It retries automatically when Android reports a network is available. Nothing is queued: there is **no fake offline sync**. |
| Connection lost while using the app | The web app shows a banner ("You're offline. Changes can't be saved…") and its API errors say the server is unreachable. Data reloads when the connection returns. |
| File uploads (X-rays, documents) | System picker (files, gallery, cloud providers) with multi-select where the input allows it, plus *take a photo* via the camera app when the input accepts images. Files are uploaded untouched; the server stores X-rays losslessly (docs/XRAY_STORAGE.md). The app itself needs **no camera or storage permission**. |
| Server downloads (X-ray originals, the head doctor's clinic backup ZIP) | Android DownloadManager with the current session cookie → `Downloads/AeroDent/`, with a system notification. Only URLs on the server origin are accepted. |
| Generated files (made in the page, e.g. offline-style exports) | `NativeShell.saveBlob()` → MediaStore → `Downloads/AeroDent/`. |
| Printing (prescriptions, invoices) | `NativeShell.print()` → Android print framework (print to PDF or a printer) using the page's print stylesheet. |
| Back button | Closes the command palette / dialog / drawer first, then returns to the dashboard, then leaves the app. |
| Safe areas / notches / keyboard | Edge-to-edge window; the WebView is padded by the system-bar, display-cutout and keyboard insets, so nothing is hidden and inputs stay visible above the keyboard. |
| RTL / LTR | Entirely the web app's (`dir="rtl"` for Arabic). The offline page follows the language last chosen in the app, or the device language. |
| Rotation / resizing | Handled in place (no reload, no lost form input). |
| Renderer crash | The WebView is recreated instead of the app crashing. |

### Security settings

* Release builds: HTTPS only (`cleartextTrafficPermitted="false"`), system CAs only, and the
  build fails if the server URL is not `https://`. Debug builds additionally allow plain HTTP to
  `10.0.2.2`, `localhost` and `127.0.0.1` for local development only (`src/debug`).
* TLS certificate errors are never bypassed.
* WebView: no `file://` or `content://` access, no mixed content, no pop-up windows, third-party
  cookies off, Safe Browsing on, remote debugging only in debug builds, **no
  `addJavascriptInterface`**.
* `window.AeroDentNative` uses `WebViewCompat.addWebMessageListener` with an allow-list of exactly
  one origin (the server). The offline page and any other site never see it. It accepts only
  `download` and `print`; file names are sanitised (no path separators or control characters).
* Backups are disabled (`allowBackup="false"` and data-extraction rules excluding everything), so
  cookies and WebView storage never leave the device through cloud backup or device transfer.
* Exported components: only the launcher activity. The FileProvider (camera captures in the
  private cache) is not exported. Captured photos older than a day are deleted.

## Configuration

| Setting | Where | Notes |
|---|---|---|
| Server URL | `-PaerodentServerUrl=https://clinic.example.com` or env `AERODENT_SERVER_URL` | Origin only (scheme, host, optional port; no path). **Required** for release builds and must be `https://`. Debug default: `http://10.0.2.2:5000` (the host machine from the Android emulator). |
| Release signing | env `AERODENT_KEYSTORE_FILE`, `AERODENT_KEYSTORE_PASSWORD`, `AERODENT_KEY_ALIAS`, `AERODENT_KEY_PASSWORD` | Without them the release APK is unsigned. Keystores are git-ignored; never commit them. |
| App id / version | `mobile/android/app/build.gradle` (`applicationId`, `versionCode`, `versionName`) | Debug builds use the `.debug` suffix, so both can be installed side by side. |
| Android SDK location | `mobile/android/local.properties` (`sdk.dir=…`) or `ANDROID_HOME` | Git-ignored. Android Studio writes it automatically. |

The server needs no changes for the app. In production it must be served over HTTPS
(`SESSION_COOKIE_SECURE` is on outside development), which the release app requires anyway.

## Requirements

* JDK 17 or newer (tested with 21).
* Android SDK platform 35 and build-tools (Android Studio installs these; or `sdkmanager
  "platforms;android-35" "build-tools;35.0.0"`).
* Devices: Android 10 (API 29) or newer, with an up-to-date Android System WebView / Chrome.

## Build commands

All commands run from `mobile/android`. The Gradle wrapper downloads Gradle 8.14.3 on first use
(its checksum is pinned).

```bash
cd mobile/android

# Debug build against a local dev server (emulator → host machine on port 5000)
./gradlew assembleDebug
#   → app/build/outputs/apk/debug/app-debug.apk

# Debug build against another server
./gradlew assembleDebug -PaerodentServerUrl=https://staging.example.com

# Release build (unsigned unless the AERODENT_KEYSTORE_* variables are set)
./gradlew assembleRelease -PaerodentServerUrl=https://clinic.example.com
#   → app/build/outputs/apk/release/app-release.apk (or app-release-unsigned.apk)

# Play Store bundle
./gradlew bundleRelease -PaerodentServerUrl=https://clinic.example.com

# Checks
./gradlew lintDebug testDebugUnitTest
```

Install on a connected device or emulator: `adb install -r app/build/outputs/apk/debug/app-debug.apk`.

Create a signing key once (keep it and its passwords safe; Play Store updates need the same key):

```bash
keytool -genkeypair -v -keystore aerodent-release.jks -alias aerodent \
        -keyalg RSA -keysize 4096 -validity 10000
```

## Development workflow

1. Start the backend as usual (`flask --app backend.app run --port 5000`, see the main README).
2. Either:
   * **Emulator:** build the default debug APK; it reaches the host at `http://10.0.2.2:5000`.
   * **Physical device over USB:** `adb reverse tcp:5000 tcp:5000`, then build with
     `-PaerodentServerUrl=http://localhost:5000`.
3. Web changes (HTML/CSS/JS in `web/`) need **no app rebuild**: reload the page (pull the app to
   the foreground or use Chrome DevTools). Asset versioning and the service worker pick up new
   files automatically (docs/CACHING.md).
4. Debug with Chrome DevTools: open `chrome://inspect` on the computer; debug builds allow
   WebView inspection.
5. Rebuild the APK only when something in `mobile/android` changes, or when `web/i18n.js`
   changes and you want the offline page to use the new strings (they are copied in at build
   time by the `copyWebResources` task).

### Where the web app integrates

`web/js/nativeBridge.js` is the only web code aware of the app. It detects
`window.AeroDentNative` (absent in browsers, so everything falls back to normal browser behaviour)
and provides:

* `downloadBlob(blob, filename)`: save a file generated in the page.
* `printPage(jobName)`: print with the print stylesheet (prescriptions, invoices).
* `window.AeroDentBack()`: called by the Back button.
* The online/offline connectivity banner (useful in browsers too).

The page also gets the `native-app` class on `<html>` and the user agent contains
`AeroDentAndroid/<version>`, if app-specific styling is ever needed.

## Testing notes / limitations

* Verified in this repository: debug and release builds, Android lint (no issues), unit tests for
  file-name sanitising, release guards (missing / `http://` / path-containing server URLs are
  rejected), manifest review (permissions, exported components, backup rules, network security
  config), the offline page in English/Arabic at phone, small-phone and landscape sizes, and the
  web-side bridge against a simulated native channel (downloads, blob/data links, printing,
  Back handling, connectivity banner).
* Not verifiable in the CI container (no hardware virtualisation for an emulator): on-device
  behaviour of the camera picker, DownloadManager, and the print dialog. Check these on a
  device before the first release: sign in, upload an X-ray from the gallery and from the
  camera, download its original, export clinic data, print a prescription, rotate the screen,
  toggle airplane mode, and use Back in a dialog.
* iOS is not included. The same approach works there (a `WKWebView` shell), but it needs a Mac
  to build.
