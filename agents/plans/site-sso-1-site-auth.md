# Plan: Site-wide sign-in, part 1: Google sign-in in the engineerfamily Flask app
**Status:** ❌ Not started (draft, waiting for the user's review)
**Risk:** review (authentication; lands in the engineerfamily repo)
**Depends on:** none. Parts 2 (`site-sso-2-proxy-mode`) and 3 (`site-sso-3-cutover`) build on it.

## Goal
Anyone can sign in with Google from the top-right corner of any engineerfamily.net page and stays signed in across the
whole domain (one cookie, 30 days). Signing in grants nothing by itself: every page stays open to signed-out and
uninvited visitors. Only the Strelitzia dashboard checks invites, and it keeps using its own sign-in until part 3.

## Design (all three parts)
- **Auth lives in the engineerfamily Flask app** (`services/app`, already behind nginx `location /`), at `/auth/*`:
  `login`, `callback`, `me`, `logout`, `verify`. It only knows who you are (Google `sub`, verified email, name).
  Who may use the dashboard stays in Strelitzia's `users` table (owner + invites), unchanged.
- **Cookie** `ef_session`: Flask's signed session cookie, `Path=/`, **no `Domain`** (host-only, so prod
  `engineerfamily.net` and `preprod.engineerfamily.net` never see each other's cookie, and `umami.*` never sees it),
  `HttpOnly`, `Secure` on https, `SameSite=Lax`, 30-day `max_age`. Signed with `SITE_SESSION_SECRET` (own value per env).
  Rotating the secret signs everyone out. The Flask app is the only holder of the key.
- **The dashboard learns the identity from nginx** (part 3): `auth_request` to Flask's verify endpoint, which answers
  204 with `X-Auth-Request-Email`, `X-Auth-Request-User` (Google `sub`) and `X-Auth-Request-Preferred-Username`
  (display name, percent-encoded: headers are Latin-1) when signed in, and 204 with no headers when not. nginx copies
  them onto the proxied request and overwrites anything the client sent. The names match oauth2-proxy's, so
  Strelitzia's proxy mode (part 2) works for self-hosters behind oauth2-proxy too.
- **www**: `www.engineerfamily.net` gets its own host-only cookie. Part 3 301s `www` to the apex so there's one.

## Context
- `~/src/engineerfamily/services/app/app.py` (68 lines): routes `/`, `/games/`, `/assets/*`; serves the Vite build.
- `~/src/engineerfamily/services/app/requirements.txt`: `flask`, `gunicorn`. Add `google-auth>=2.0`, `requests>=2.31`
  (google-auth's transport) and `pytest` for a dev-only test.
- `~/src/engineerfamily/services/app/vite/src/App.jsx:8-28`: the site header (`site-nav`, `nav-menu`).
- `~/src/engineerfamily/services/strelitzia/index.html:13-16`, `privacy.html`: Strelitzia's static pages, served by
  nginx directly (not Flask), so their header widget is a small script calling `/auth/me`.
- `~/src/engineerfamily/docker-compose.{prod,preprod}.yml`, `app:` service (`environment:`): add
  `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SITE_SESSION_SECRET`, `PUBLIC_URL` from the env file.
- Mirror `src/strelitzia/web/auth.py:139-200` (this repo): state in the session, `httpx`/`requests` token exchange,
  `id_token.verify_oauth2_token` with 30 s clock skew, require `email_verified`. Never log tokens.
- Gotchas: `next` must be a same-site path (starts with `/`, not `//` or `/\`) to avoid an open redirect.
  `/auth/me` and `/auth/verify` send `Cache-Control: no-store` (Cloudflare must not cache them). The callback goes
  through Cloudflare like every page; Cloudflare doesn't strip cookies on dynamic responses.
- engineerfamily has no test suite or CI tests; its rules are `docker compose ... config -q` and `nginx -t`.

## Tasks
### Task 1: `/auth/*` routes in Flask
**Runs:** interactive (engineerfamily repo; needs the user's `.env` values to try it)
**Files:** `services/app/auth.py` (new), `services/app/app.py` (modify), `services/app/requirements.txt` (modify),
`services/app/test_auth.py` (new)
**What:** a Flask blueprint `auth` with
- `GET /auth/login?next=<path>`: store a random `state` and the checked `next` in the session, 303 to Google
  (`openid email profile`, `prompt=select_account`, `redirect_uri={PUBLIC_URL}/auth/callback`).
- `GET /auth/callback`: check `state`, exchange the code, verify the ID token, set `session = {sub, email, name}`
  (`session.permanent = True`), 303 to `next` (default `/`). Failures go to `next?signin=error` with nothing stored.
- `GET /auth/me` → `{"signed_in": bool, "email": str|null, "name": str|null}`.
- `POST /auth/logout` → clears the session, 204 (SameSite=Lax already keeps cross-site posts from carrying the cookie).
- `GET /auth/verify` → 204, with the three `X-Auth-Request-*` headers (see Design) only when signed in.
Sign-in is off (login 404s, `me` says signed out) while `GOOGLE_CLIENT_ID` is unset, so merging changes nothing.
Refuse to start with the client id set but the secret, `SITE_SESSION_SECRET` or `PUBLIC_URL` missing.
**Validate:** `cd services/app && python -m pytest test_auth.py -q` → passes: next-path checks, a stubbed callback
(token exchange and `verify_oauth2_token` monkeypatched) sets the cookie with `Path=/`, no `Domain`, `HttpOnly`,
`SameSite=Lax`; a wrong `state` signs nobody in; `verify` adds the headers only with a session.
**Status:** ❌

### Task 2: Profile / sign-in top right on the site and on Strelitzia's static pages
**Runs:** interactive (engineerfamily repo; checked in a browser on preprod)
**Files:** `services/app/vite/src/App.jsx` (modify), `services/app/vite/src/styles.css` (modify),
`services/strelitzia/session.js` (new), `services/strelitzia/index.html` (modify)
**What:** a right-aligned header item: signed out, a "Sign in" link to `/auth/login?next=<current path>`; signed in, a
round initials button (no Google profile picture: no third-party image loads) that opens a small menu with the
email, a link to `/strelitzia/dashboard/`, and "Sign out" (`POST /auth/logout`, then reload). `session.js` does the
same in plain JS for the static pages. The visual match across sites is the separate "Shared header" backlog item; this
task only puts the control top right and keeps the markup simple enough to restyle.
**Validate:** `npm --prefix services/app/vite run build` succeeds; on preprod (part 3's steps 1-3) the control shows on
`/`, `/games/` and `/strelitzia/`.
**Status:** ❌

### Task 3: Compose env, docs, privacy text
**Runs:** interactive (engineerfamily repo)
**Files:** `docker-compose.prod.yml`, `docker-compose.preprod.yml`, `README.md`, `services/strelitzia/privacy.html` (modify)
**What:** pass the four env vars to `app` (`PUBLIC_URL` is `https://engineerfamily.net` / `https://preprod.engineerfamily.net`).
README: an "Auth" section with the design above. Privacy: say the site keeps a sign-in cookie with your Google email
and name for 30 days and nothing else; the dashboard and Drive parts stay as they are.
**Validate:** `docker compose --env-file /srv/engineerfamily-<env>/.env -f docker-compose.base.yml -f docker-compose.<env>.yml config -q`
→ exit 0 for prod and preprod.
**Status:** ❌

## Validation
- Task validations pass; `nginx -t` unchanged (no nginx edits in this part).
- On preprod after `make preprod-deploy ref=origin/<branch>`: `curl -s -u <preprod creds> https://preprod.engineerfamily.net/auth/me`
  → `{"signed_in": false, ...}`.

## Human test steps (preprod)
See `site-sso-3-cutover`, steps 1-4 (part 1 is tested together with the cutover's preprod run).

## Decisions
1. Flask, not Strelitzia, owns site sign-in: the site shouldn't depend on one app's container, and Strelitzia stays a
   standalone open-source app whose built-in Google sign-in keeps working for self-hosters.
2. Flask over oauth2-proxy: no extra container on the 4 GB VPS, and pages must stay open to signed-out visitors, which
   is the opposite of oauth2-proxy's default; its header names are kept so it remains a drop-in later.
3. Host-only cookie, never `Domain=engineerfamily.net`: keeps prod, preprod and Umami apart.
4. Same Google project and Web client as the dashboard ("Strelitzia web"): Drive's `drive.file` needs that project anyway,
   and one consent screen covers both. The user copies the id and secret into the engineerfamily `.env` files.

## Open questions (for the user, before building)
1. Consent-screen branding: keep the app name "Strelitzia", or rename it "engineerfamily" with home page
   `https://engineerfamily.net/` (recommended, since sign-in is now site-wide)? Either way no logo, so no brand verification.
2. Should the dashboard keep a "Sign out" button of its own (signs out of the whole site), or only the site menu? Recommended: keep it.
