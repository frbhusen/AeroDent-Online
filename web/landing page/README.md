# AeroDent — Landing Page

A standalone, **static** public marketing site + user manual for AeroDent. It needs
**no AeroDent backend** and **no database**. It can be hosted on any static host
(Netlify, Vercel, GitHub Pages, Cloudflare Pages, S3, nginx…) or served straight from
this folder.

> Note the folder name contains a space: `web/landing page/`. In URLs the space becomes
> `%20` (e.g. `/landing%20page/`).

## Files

| File | Purpose |
|------|---------|
| `index.html` | The landing page (hero, features, product preview, how-it-works, why, audience, trial form, FAQ, footer). |
| `user-manual.html` | The AeroDent user manual (table of contents + workflow sections). |
| `styles.css` | All styles for both pages. Reuses AeroDent brand tokens; loads the Cairo font. |
| `i18n.js` | Translation engine. Arabic is active (text lives in the HTML); English is prepared. |
| `landing.js` | Landing-page behaviour: nav, FAQ accordion, language switch, trial form. |
| `manual.js` | Manual behaviour: nav, collapsible TOC, scrollspy, language switch. |
| `config.js` | **The one place you configure** the trial-form email delivery + language flag. |
| `assets/` | Self-contained copies of the AeroDent logo/favicon (from `web/icons/`). |

Nothing in the existing AeroDent application was modified. The main app
(`web/index.html`, backend, service worker) is untouched.

---

## ⚙️ Trial-form setup (REQUIRED for submissions to reach the email)

The trial form is delivered by **[Web3Forms](https://web3forms.com)** — a free service
built for static sites. There is no server code and no `mailto:` link.

**One-time setup (~2 minutes):**

1. Go to <https://web3forms.com>.
2. In "Create your Access Key", enter the destination email:
   **`husen_.rajb@outlook.com`**
3. Web3Forms emails an **Access Key** (a UUID) to that address. Open the email and
   confirm it.
4. Open **`config.js`** and replace the placeholder:
   ```js
   web3formsAccessKey: "WEB3FORMS_ACCESS_KEY_PLACEHOLDER",
   // becomes e.g.
   web3formsAccessKey: "a1b2c3d4-....-....",
   ```
5. Save. Submissions now arrive at `husen_.rajb@outlook.com`.

**Security note:** a Web3Forms access key is *designed to be public* and safe to ship in
client-side code. It only authorises delivering a submission to the email you registered;
it cannot read past submissions and is not a password. No other secret is stored here.

**Until the key is set:** the form is fully usable and validated, but on submit it shows a
clear "not configured yet" message (with the contact email) instead of failing silently —
so it is never confusing to a visitor.

**Spam protection:** two layers are active — a hidden honeypot field (`botcheck`) that real
users never see, plus Web3Forms' own built-in spam filtering.

### Swapping providers (optional)

To use Formspree or another provider instead, edit only `submitViaWeb3Forms()` in
`landing.js` and the endpoint/fields in `config.js`. The validation and UI stay the same.

---

## 🌍 Languages

- **Arabic (ar)** is fully implemented and is the default. Its text lives directly in the
  HTML for SEO and instant rendering.
- **English (en)** is *architecturally prepared* but not yet translated. The language
  switcher is real: clicking **EN** currently shows an honest "coming soon" notice.

**To enable English later (no rebuild needed):**

1. Fill in the `STRINGS.en` dictionary in `i18n.js` (the keys are already listed; any
   missing key safely falls back to the Arabic text).
2. Set `englishEnabled: true` in `config.js`.

The switcher will then toggle `lang`/`dir` and swap text automatically.

---

## ▶️ Run / preview locally

Any static file server works. From the repository root:

```bash
# Serve the whole web/ folder, then open the landing page:
python -m http.server 5500 --directory web
#   Landing page: http://localhost:5500/landing%20page/
#   User manual:  http://localhost:5500/landing%20page/user-manual.html
```

Or serve just this folder:

```bash
python -m http.server 5500 --directory "web/landing page"
#   http://localhost:5500/          (index.html)
#   http://localhost:5500/user-manual.html
```

The Flask app also serves it (no config needed) at `/landing%20page/index.html`, but the
landing page is intentionally independent of the backend.

Syntax-check the scripts:

```bash
node --check "web/landing page/landing.js"
node --check "web/landing page/manual.js"
node --check "web/landing page/i18n.js"
node --check "web/landing page/config.js"
```

---

## 🚀 Deploy

Upload the contents of `web/landing page/` to any static host, or point a host at this
folder. Set the site root so `index.html` is served at `/`. Update the `<link rel="canonical">`
URLs in `index.html` / `user-manual.html` to the real deployment URL if desired.
