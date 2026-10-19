# Plan: Site-wide sign-in, part 3: the dashboard trusts the site's sign-in and uses the shared header
**Status:** ❌ Not started
**Risk:** review (authentication)
**Depends on:** site-sso-1-site-auth, site-sso-2-site-header (design only: this part can merge before they ship, because
the defaults are unchanged)

## Goal
With `STRELITZIA_AUTH_MODE=proxy`, the dashboard stops running its own Google sign-in and takes the signed-in email from
the reverse proxy (engineerfamily's nginx `auth_request`, or oauth2-proxy for a self-hoster). The invite check, the
owner, disabled accounts, admin routes and Drive connect work as today. A visitor who is signed in to the site but not
invited sees "This Google account isn't invited" with their email and a "Use another account" link, never a loop.
With `STRELITZIA_SITE_HEADER_URL` set, the dashboard header starts with the same engineerfamily home link and ends
with the same sign-in / profile / Sign out control as every other engineerfamily.net page (part 2).
Without the settings nothing changes: login is off without a client id, and Google sign-in is built in with one.

## Context
- `src/strelitzia/web/auth.py:49-101`: `auth_enabled`, `public_url`, `is_public_path`, `current_user` (the one seam every
  route and `web/admin.py:_owner` goes through), `check_config`. `:103-131`: `_sign_in` / `_account_for` (owner re-key,
  invited → active via `users.activate`). `:157-232`: `login`, `callback`, `logout`, `me`.
- `src/strelitzia/web/app.py:1106-1118`: `require_session` middleware and `SessionMiddleware`.
  Keep `SessionMiddleware`: Drive connect stores `drive_state` in it.
- `src/strelitzia/web/auth.py:233-317`: Drive connect. Unchanged, except `login_hint` comes from `current_user`.
- `tests/web/test_auth.py`, `tests/web/web_helpers.py`: patterns for env monkeypatching and the stubbed Google flow.
- `dashboard/src/api.ts:37-45, 290-302` (`onUnauthorized`, `getMe`, `LOGIN_URL`, `logout`), `dashboard/src/types.ts:487-498`
  (`AuthMe`), `dashboard/src/pages/SignInPage.tsx` (the `?auth=` messages), `dashboard/src/App.tsx:20-69` (the `.topbar`
  header and its `user-menu`), `dashboard/src/styles.css:63-64` (`.topbar`, `.brand`).
- `<ef-home>` / `<ef-profile next>`: custom elements from engineerfamily's `/shared/site-header.js` (part 2), Shadow DOM,
  styled by themselves. Page CSS only positions them.
- Headers (set only by the proxy, see part 1's Design): `X-Auth-Request-Email` (required), `X-Auth-Request-Preferred-Username`
  (display name, percent-encoded; `urllib.parse.unquote` it).
- Gotchas: in proxy mode the headers are the whole proof of identity, so they are read **only** when the mode is
  `proxy`; in the other modes they are ignored even if present (a test covers it). Lower-case and strip the email
  as `_account_for` does. Don't write `last_login_at` on every request: write it from `GET /auth/me` only, at most once an hour.

## Tasks
### Task 1: proxy mode in `web/auth.py`
**Runs:** unattended
**Files:** `src/strelitzia/web/auth.py` (modify), `tests/web/test_auth.py` (modify)
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
  `logout_url` (`STRELITZIA_SITE_LOGOUT_URL` or `/auth/logout` in proxy mode, else null) and `site_header_url`
  (`STRELITZIA_SITE_HEADER_URL` or null, any mode).
- `check_config`: proxy mode needs `OWNER_EMAIL` and `SESSION_SECRET` (Drive state), not the Google secret
  (Drive connect stays unavailable without it, as today). Update the module docstring for the three modes.
**Validate:** `python -m pytest tests/web/test_auth.py -q` → passes, including new tests: proxy mode with an invited
email reaches `/strelitzia/dashboard/api/jobs`; no header → 401; an uninvited email → 401 `not_invited` and `me`
shows the identity; a disabled account → `disabled`; owner re-key from `owner@localhost` works; admin routes 403 for
a non-owner; the headers are ignored in `google` and `off` modes; `login` redirects to the site with `next`.
**Status:** ✅ 2026-10-19

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
**Status:** ✅ 2026-10-19

### Task 3: the shared header in the dashboard
**Runs:** unattended
**Files:** `dashboard/src/components/SiteSlots.tsx` (new), `dashboard/src/__tests__/SiteSlots.test.tsx` (new),
`dashboard/src/styles.css` (modify), `dashboard/src/App.tsx`, `dashboard/src/pages/SignInPage.tsx`,
`src/strelitzia/web/static/` (again, after Task 2)
**What:** `SiteSlots` exports `useSiteHeader(url)` (appends one `<script src=url>` to `<head>`, once) and two components,
`SiteHome` (`<ef-home>`) and `SiteProfile` (`<ef-profile next="/strelitzia/dashboard/">`); add the two tags to React's
`JSX.IntrinsicElements`. With `me.site_header_url`: `.topbar` starts with `<SiteHome/>` before the Strelitzia brand and
ends with `<SiteProfile/>` after Add job, and the dashboard's own `user-menu` (name + Sign out) is not rendered, since
`<ef-profile>` carries the Sign out button. `SignInPage` gets the same two slots in a slim top bar, so an uninvited or
signed-out visitor can go home or switch account. Without `site_header_url` the header is exactly today's.
CSS: the home slot is the topbar's first item and the profile slot is pushed right with `margin-left: auto`; at phone
width the nav scrolls horizontally and both slots stay on the top row.
**Validate:** `npm --prefix dashboard test -- --run SiteSlots` → passes: with `site_header_url` the header's first
element is `ef-home`, its last is `ef-profile`, and there's no `.user-menu`; without it, `.user-menu` with Sign out is there.
**Status:** ✅ 2026-10-19

### Task 4: document the modes
**Runs:** unattended
**Files:** `agents/DEPLOY.md` (modify)
**What:** in "Google sign-in", describe the three modes, the two headers, `STRELITZIA_SITE_LOGIN_URL` / `_LOGOUT_URL` /
`_SITE_HEADER_URL`,
and the rule that proxy mode is safe only when nothing but the proxy can reach the container (on the VPS: no published
port; part 4 also moves it off the shared `web` network).
**Validate:** `grep -n "AUTH_MODE" agents/DEPLOY.md` → the new section.
**Status:** ✅ 2026-10-19

## Validation
- `scripts/validate.sh --full` passes.
- `STRELITZIA_AUTH_MODE=proxy STRELITZIA_OWNER_EMAIL=owner@example.com STRELITZIA_SESSION_SECRET=x strelitzia serve`, then
  `curl -s -H 'X-Auth-Request-Email: owner@example.com' localhost:8765/strelitzia/dashboard/api/auth/me` → `"role": "owner"`;
  with `stranger@example.com` → `"reason": "not_invited"`.

## Human test steps (preprod)
Merging alone changes nothing on preprod or prod (settings unset). The live test is part 4, steps 5-10.

## Decisions
1. Header trust behind an explicit mode, not cookie verification with a shared key: Strelitzia never holds the site's
   key or depends on Flask's cookie format, and the same code serves oauth2-proxy users.
2. The built-in Google flow stays: self-hosters without a proxy still need it, and it is part 4's rollback path.
3. Uninvited visitors get 401 with a reason, not 403: the SPA already turns every 401 into the sign-in screen.
4. The dashboard renders engineerfamily's `<ef-home>` / `<ef-profile>` instead of copying their look, so the home link and
   the profile and Sign out control can't drift (user, 2026-10-18). They are opt-in by URL, so a self-hosted
   Strelitzia keeps its own header.
