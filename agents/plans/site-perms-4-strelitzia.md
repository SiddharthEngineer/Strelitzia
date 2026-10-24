# Plan: Site permissions 4/4: Strelitzia trusts engineerfamily for access, admin and cap
**Status:** 🔄 In progress
**Risk:** review (who can use the dashboard, and how much Claude spend they may run up)
**Depends on:** engineerfamily site-perms-3-gate (nginx sends the new headers)

## Goal
Who may use the dashboard, and each user's monthly Claude cap, are set on engineerfamily's Users page
(`/users/`), not in Strelitzia. When nginx says a visitor has Strelitzia access, the dashboard lets them in (creating
their account on first visit) and applies the cap nginx sends. Strelitzia's own Users page is replaced by a link to
engineerfamily's. Per-user data (jobs, documents, spend) stays keyed by email, so existing users keep theirs.

## Context
- `src/strelitzia/web/auth.py:59-178`: `auth_mode`, `proxy_identity`, `current_user` (proxy branch), `_account_for`
  (owner re-keying, then `users.activate`, which refuses never-invited and disabled emails).
- `src/strelitzia/users.py:1-137`: `User`, `invite`, `activate`, `set_cap`, `set_status`; the owner is the account at
  `STRELITZIA_OWNER_EMAIL` and owns the content library and legacy Drive token (`web/app.py:249-275`). That stays as is.
- `src/strelitzia/llm.py:275-310`: the cap check reads `users.monthly_cap_usd`; it keeps doing that.
- `src/strelitzia/web/admin.py:1-114` and `dashboard/src/pages/UsersPage.tsx`, `App.tsx:43,74,95`, `api.ts`, `types.ts`,
  `__tests__/UsersPage.test.tsx`: the Users page to retire.
- New headers from engineerfamily nginx (only on `/strelitzia/dashboard/`, cleared on assets, client copies always
  replaced): `X-Auth-Request-Access: strelitzia`, `X-Auth-Request-Admin: 1|0`, `X-Auth-Request-Cap-Usd: <number>|none`.
- Gotcha (deploy order): prod Strelitzia ships on its own (`strelitzia-deploy`) and may run behind an older
  engineerfamily nginx that doesn't send these headers. So: **only** when `X-Auth-Request-Access` is present and equals
  `strelitzia` do we trust engineerfamily; without it, keep today's invite-list behaviour exactly. That's safe in either
  order, since an old nginx can't send the header and nginx always overwrites client copies.
- `tests/web/`: proxy-mode tests to extend (search for `X-Auth-Request-Email`).

## Tasks
### Task 1: Trust engineerfamily's grant and cap
**Runs:** unattended
**Files:** src/strelitzia/web/auth.py (modify), src/strelitzia/users.py (modify), tests/web/test_auth_proxy.py (new or modify the existing proxy test file)
**What:**
- `ACCESS_HEADER`, `ADMIN_HEADER`, `CAP_HEADER` constants. `site_grant(request) -> SiteGrant | None` with
  `@dataclass class SiteGrant: admin: bool; cap_usd: float | None` (None when the Access header is absent or not
  `strelitzia`; a malformed cap → treat as `DEFAULT_CAP_USD` and log once).
- Proxy branch of `current_user`: with a grant, `users.ensure_active(conn, email, name) -> User` (new: invite if missing,
  re-activate a `disabled` or `invited` row; never touches the owner's role), then if the user isn't the owner and
  `user.monthly_cap_usd != grant.cap_usd`, `users.set_cap`. Admins get `cap_usd=None` from nginx already. Cache on
  `request.state`. Without a grant: unchanged code path.
- `/me` (`auth.py:297-320`): add `site_admin: bool` and `users_url` (`f"{public_url-origin}/users/"`, from `PUBLIC_URL`'s
  scheme+host) when a grant is present.
**Validate:** `scripts/validate.sh` → passes; the new tests cover: grant creates and activates an unknown email; a
disabled account with a grant comes back active; the cap header is written to `monthly_cap_usd` ("none" → NULL); the
owner's role and cap are untouched; no Access header → a never-invited email still gets 401 `not_invited`.
**Status:** ✅ 2026-10-24 (this commit)

### Task 2: Retire the dashboard Users page
**Runs:** unattended
**Files:** src/strelitzia/web/admin.py (modify), dashboard/src/App.tsx (modify), dashboard/src/pages/UsersPage.tsx (delete), dashboard/src/__tests__/UsersPage.test.tsx (delete), dashboard/src/api.ts (modify), dashboard/src/types.ts (modify), src/strelitzia/web/static (rebuilt bundle)
**What:** When the request carries a site grant, the admin API answers 410 `{"detail": "Users are managed at <users_url>"}`;
without one (old nginx, or `strelitzia users` CLI setups) it keeps working, so the CLI and older deploys are unaffected.
Dashboard: drop the Users route/page; when `me.site_admin`, the nav shows "Users" linking to `me.users_url` (full page
load, new tab not needed). Remove the now-unused API client code and types. Rebuild the committed bundle.
**Validate:** `scripts/validate.sh --full` → passes (dashboard tests and build included).
**Status:** ❌

### Task 3: Docs
**Runs:** unattended
**Files:** agents/DEPLOY.md (modify), AGENTS.md (modify)
**What:** DEPLOY.md: access and caps now come from engineerfamily's Users page via nginx headers; the old invite list
applies only without them. AGENTS.md Map line for `web/admin.py` updated to match. Keep AGENTS.md short.
**Validate:** `scripts/validate.sh` → passes.
**Status:** ❌

## Validation
- `scripts/validate.sh --full` passes.
- Preprod (with engineerfamily part 3 live): `curl -s -o /dev/null -w "%{http_code}"
  https://preprod.engineerfamily.net/strelitzia/dashboard/api/health` → 200.

## Human test steps (preprod)
1. On `https://preprod.engineerfamily.net/users/` invite a second Google account you own and tick Strelitzia, cap $1.
2. Sign in with it and open the dashboard: it loads with no Strelitzia-side invite needed.
3. Back on the Users page, set its cap to $0 and run anything that calls Claude from that account: it's refused for the cap.
4. Untick Strelitzia: the dashboard now says you don't have access (engineerfamily's page).
5. As yourself, the dashboard nav's "Users" link opens engineerfamily's Users page.

## Decisions
1. engineerfamily is the source of truth for access and caps; Strelitzia keeps enforcing the cap and its owner concept.
2. The header-presence check keeps prod safe whichever repo deploys first.
3. Existing Strelitzia accounts are matched by email, so nobody loses data; the user re-invites them on engineerfamily.
