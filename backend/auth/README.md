# Authentication

The authentication API uses Flask's signed session cookie. The session contains only `user_id`; `/api/auth/me` reloads the active `User` and its `clinic_id` from PostgreSQL on every request.

The current deployment is same-origin. State-changing auth requests use `SameSite=Lax` cookies and reject a mismatched `Origin` or `Referer` header. No permissive CORS policy is enabled. If the frontend and API move to separate origins, configure an explicit origin and a deliberate CSRF token flow before enabling credentials.

Set `SECRET_KEY` in the environment for persistent local sessions and always set it in production. Development can use the application-generated fallback secret, which is intentionally rotated on process restart.
