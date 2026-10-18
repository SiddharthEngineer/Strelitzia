# Plan: Site-wide sign-in, part 2: the dashboard trusts the site's sign-in (proxy auth mode)
**Status:** ❌ Not started (draft, waiting for the user's review)
**Risk:** review (authentication)
**Depends on:** site-sso-1-site-auth (design only: this part can merge before part 1 ships, because the default mode is unchanged)

## Goal
With `STRELITZIA_AUTH_MODE=proxy`, the dashboard stops running its own Google sign-in and takes the signed-in email from
the reverse proxy (engineerfamily's nginx `auth_request`, or oauth2-proxy for a self-hoster). The invite check, the
owner, disabled accounts, admin routes and Drive connect work as today. A visitor who is signed in to the site but not
invited sees "This Google account isn't invited" with their email and a "Use another account" link, never a loop.
Without the setting nothing changes: login is off without a client id, and Google sign-in is built in with one.

## Context
- `src/strelitzia/web/auth.py:49-90`: `auth_enabled`, `public_url`, `is_public_path`, `current_user` (the one seam every
  route and `web/admin.py:_owner` goes through), `check_config`. `:99-127`: `_sign_in` / `_account_for` (owner re-key,
  invited → active via `users.activate`). `:153-215`: `login`, `callback`, `logout`, `me`.
- `src/strelitzia/web/app.py:1-12` (docstring), `:1106-1118`: `require_session` middleware and `SessionMiddleware`.
  Keep `SessionMiddleware`: Drive connect stores `drive_state` in it.
- `src/strelitzia/web/auth.py:218-317`: Drive connect. Unchanged, except `login_hint` comes from `current_user`.
- `tests/web/test_auth.py`, `tests/web/web_helpers.py`: patterns for env monkeypatching and the stubbed Google flow.
- `dashboard/src/api.ts:37-45, 290-302` (`onUnauthorized`, `getMe`, `LOGIN_URL`, `logout`), `dashboard/src/types.ts:487-498`
  (`AuthMe`), `dashboard/src/pages/SignInPage.tsx` (the `?auth=` messages), `dashboard/src/App.tsx:20-45`.
- Headers (set only by the proxy, see part 1's Design): `X-Auth-Request-Email` (required), `X-Auth-Request-Preferred-Username`
  (display name, percent-encoded; `urllib.parse.unquote` it).
- Gotchas: in proxy mode the headers are the whole proof of identity, so they are read **only** when the mode is
  `proxy`; in the other modes they are ignored even if present (a test covers it). Lower-case and strip the email
  as `_account_for` does. Don't write `last_login_at` on every request: write it from `GET /auth/me` only, at most once an hour.

## Tasks
### Task 1: proxy mode in `web/auth.py`
**Runs:** unattended
**Files:** `src/strelitzia/web/auth.py` (modify), `src/strelitzia/web/app.py` (modify), `tests/web/test_auth.py` (modify)
**What:**
- `auth_mode() -> Literal["off", "google", "proxy"]`: `proxy` when `STRELITZIA_AUTH_MODE=proxy`, else `google` when
  the client id is set, else `off`. `auth_enabled()` becomes `auth_mode() != "off"`.
- `proxy_identity(request) -> tuple[str, str | None] | None`: email and name from the headers, `None` without an email.
- `current_user` in proxy mode: no identity → 401 `"Not signed in"`; identity but `_account_for` returns `None` →
  401 `"not_invited"` or `"disabled"`. Cache on `request.state` as today.
- `login` in proxy mode: 303 to `{STRELITZIA_SITE_LOGIN_URL or "/auth/login"}?next=/strelitzia/dashboard/`
  (so `LOGIN_URL` in the SPA keeps working). `callback` 404s in proxy mode. `logout` returns
  `{"ok": true, "logout_url": <site logout>}` without touching the site cookie.
- `me` adds `mode`, `identity` (`{"email", "name"}` or null), `reason` (`"not_invited"`, `"disabled"` or null) and
  `logout_url` (`STRELITZIA_SITE_LOGOUT_URL` or `/auth/logout` in proxy mode, else null).
- `check_config`: proxy mode needs `OWNER_EMAIL` and `SESSION_SECRET` (Drive state), not the Google secret
  (Drive connect stays unavailable without it, as today). Update the app.py docstring lines about sign-in.
**Validate:** `python -m pytest tests/web/test_auth.py -q` → passes, including new tests: proxy mode with an invited
email reaches `/strelitzia/dashboard/api/jobs`; no header → 401; an uninvited email → 401 `not_invited` and `me`
shows the identity; a disabled account → `disabled`; owner re-key from `owner@localhost` works; admin routes 403 for
a non-owner; the headers are ignored in `google` and `off` modes; `login` redirects to the site with `next`.
**Status:** ❌

### Task 2: dashboard sign-in screen and sign-out in proxy mode
**Runs:** unattended
**Files:** `dashboard/src/types.ts`, `dashboard/src/api.ts`, `dashboard/src/pages/SignInPage.tsx`, `dashboard/src/App.tsx`,
`dashboard/src/__tests__/SignInPage.test.tsx` (modify), `src/strelitzia/web/static/` (rebuilt bundle)
**What:** extend `AuthMe` with the new optional fields. `SignInPage` takes `me`: with `me.reason`, show the
existing message for it plus "Signed in as <email>" and a "Use another account" link (`LOGIN_URL`, which goes through
Google's account picker); without it, the `?auth=` messages as today. Sign out: when `me.logout_url` is set, `POST` it
(then reload) instead of the dashboard's own logout. Show the sign-in page when `me.enabled && !me.user` as today.
**Validate:** `npm --prefix dashboard test -- --run SignInPage` → passes (not-invited state shows the email and the link;
google mode unchanged); `scripts/validate.sh --full` → passes with the rebuilt bundle.
**Status:** ❌

### Task 3: document the mode
**Runs:** unattended
**Files:** `agents/DEPLOY.md` (modify)
**What:** in "Google sign-in", describe the three modes, the two headers, `STRELITZIA_SITE_LOGIN_URL` / `_LOGOUT_URL`,
and the rule that proxy mode is safe only when nothing but the proxy can reach the container (on the VPS: no published
port; part 3 also moves it off the shared `web` network).
**Validate:** `grep -n "AUTH_MODE" agents/DEPLOY.md` → the new section.
**Status:** ❌

## Validation
- `scripts/validate.sh --full` passes.
- `STRELITZIA_AUTH_MODE=proxy STRELITZIA_OWNER_EMAIL=owner@example.com STRELITZIA_SESSION_SECRET=x strelitzia serve`, then
  `curl -s -H 'X-Auth-Request-Email: owner@example.com' localhost:8765/strelitzia/dashboard/api/auth/me` → `"role": "owner"`;
  with `stranger@example.com` → `"reason": "not_invited"`.

## Human test steps (preprod)
Merging alone changes nothing on preprod or prod (mode unset). The live test is part 3, steps 5-9.

## Decisions
1. Header trust behind an explicit mode, not cookie verification with a shared key: Strelitzia never holds the site's
   key or depends on Flask's cookie format, and the same code serves oauth2-proxy users.
2. The built-in Google flow stays: self-hosters without a proxy still need it, and it is part 3's rollback path.
3. Uninvited visitors get 401 with a reason, not 403: the SPA already turns every 401 into the sign-in screen.
