# Plan: Site-wide sign-in, part 4: nginx cutover, Google Console, rollout and rollback
**Status:** 🟡 Code done 2026-10-19 (engineerfamily PR #36, on preprod, human steps 1-10 pass with 9 skipped); prod rollout is M31-M33
**Risk:** review (authentication; nginx and compose in the engineerfamily repo; prod is the user's call)
**Depends on:** site-sso-1-site-auth, site-sso-2-site-header, site-sso-3-proxy-mode

## Goal
The dashboard uses the site-wide sign-in: one Google sign-in on engineerfamily.net covers the homepage, Strelitzia's
pages and the dashboard, and only the dashboard asks for an invite. Every page's header has the same engineerfamily home
link top left and the same sign-in / profile / Sign out control top right. Every step has a one-command rollback.

## Context
- `~/src/engineerfamily/services/nginx/nginx.prod.conf`: `location /` (Flask, so `/auth/*` already reaches it),
  `location /strelitzia/dashboard/` (the only proxy to `strelitzia:8000`), the `strelitzia.*`/`applypilot.*` 301 server.
- `~/src/engineerfamily/services/nginx/nginx.preprod.conf`: the same plus `auth_basic` on every location, a second server for
  `strelitzia-preprod.engineerfamily.net 127.0.0.1 localhost` (the runner's health check uses `127.0.0.1:8080`), and a
  legacy `location /app/` that also proxies to `strelitzia`.
- `~/src/engineerfamily/docker-compose.{prod,preprod}.yml`: `strelitzia` and `postgres-db` and `umami` all sit on `web`.
  `strelitzia` publishes no port.
- Make targets: `preprod-deploy`, `preprod-strelitzia-up`, `tag-prod`, `deploy-prod`, `strelitzia-up`, `strelitzia-deploy`.
- Gotchas: `proxy_set_header X-Auth-Request-Email $auth_email;` replaces any client copy, and an empty value drops the
  header, so a signed-out request reaches Strelitzia with no identity. Every location that proxies to `strelitzia` needs
  these lines (including preprod's `/app/`). `auth_request` + `auth_basic` in one location must both pass (`satisfy all`),
  which is what preprod wants. If Flask is down, `auth_request` fails and the dashboard answers 500.

## Tasks
### Task 1: nginx `auth_request` for the dashboard (prod and preprod)
**Runs:** interactive (engineerfamily repo)
**Files:** `services/nginx/nginx.prod.conf`, `services/nginx/nginx.preprod.conf` (modify)
**What:** an `internal` `location = /_auth_verify` proxying to `http://app:8000/auth/verify` (`proxy_pass_request_body off`,
`Content-Length ""`, no basic auth); `location = /auth/verify { return 404; }` so it isn't public. In each dashboard
location: `auth_request /_auth_verify;`, `auth_request_set` for the three `X-Auth-Request-*` headers, and
`proxy_set_header` for each. A nested `location /strelitzia/dashboard/assets/` without `auth_request` saves a Flask hit
per static file. `www.engineerfamily.net` → 301 to the apex (one cookie). On preprod, split the second server:
`strelitzia-preprod.engineerfamily.net` 301s to `https://preprod.engineerfamily.net/strelitzia$request_uri` (the cookie is
host-only), `127.0.0.1 localhost` keep the dashboard proxy for the health check (health is public, no `auth_request`), and
`/app/` is dropped if no open Strelitzia PR predates the move, else gets the same lines.
**Validate:** `docker run --rm -v $PWD/services/nginx/nginx.<env>.conf:/etc/nginx/conf.d/default.conf:ro nginx:alpine nginx -t`
→ "syntax is ok" for both envs (stub `.htpasswd` and upstream names as the repo's rules describe).
**Status:** ✅ 2026-10-19: engineerfamily #36 (5080cc7). `nginx -t` passes for both envs. `/app/` is dropped (no open Strelitzia PRs).
`127.0.0.1`/`localhost` answer only `/strelitzia/dashboard/api/health` (basic auth, identity headers emptied), with 404 for everything else.

### Task 2: keep other containers off the dashboard
**Runs:** interactive (engineerfamily repo)
**Files:** `docker-compose.prod.yml`, `docker-compose.preprod.yml` (modify)
**What:** a `dashboard` network joined by `nginx`, `strelitzia` and `postgres-db`; `strelitzia` leaves `web`. Only nginx
can then send it `X-Auth-Request-*` headers (Umami, a third-party image, can't reach it). Egress (Google, Anthropic) is unaffected.
**Validate:** `docker compose ... config -q` → exit 0 for both envs; after the preprod deploy,
`docker compose -p engineerfamily-preprod exec umami wget -qO- -T 3 http://strelitzia:8000/` fails to resolve.
**Status:** ✅ 2026-10-19: engineerfamily #36. `config -q` exits 0 for both envs. On preprod, umami (started briefly) gets
`wget: bad address 'strelitzia:8000'`, while nginx still reaches it.

### Task 3: rollout (the user drives; agents only on preprod)
**Runs:** interactive (Google Console, `.env` files and prod are the user's)
**Files:** none (ROADMAP Manual steps and `agents/DEPLOY.md` updates after each step)
**What:** in this order, stopping at the first failure:
1. **Google Console (user):** on the "Strelitzia web" client add `https://preprod.engineerfamily.net/auth/callback` and
   `https://engineerfamily.net/auth/callback`. Keep the four `/strelitzia/dashboard/api/{auth,drive}/callback` URIs:
   the dashboard callbacks are the rollback path, the Drive ones stay for good. **Branding:** app name `engineerfamily`,
   home page `https://engineerfamily.net/`, privacy policy `https://engineerfamily.net/privacy` (do this after step 6's
   prod deploy, so the privacy URL already answers 200), authorized domain `engineerfamily.net` (unchanged). No logo.
2. **Preprod `.env` (user):** `/srv/engineerfamily-preprod/.env` gets `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (copy of
   the Strelitzia web client) and its own `SITE_SESSION_SECRET` (`openssl rand -hex 32`).
3. Part 3 merged on Strelitzia trunk (no behavior change; prod can take it with `make strelitzia-deploy` any time).
4. Parts 1 and 2 (one engineerfamily PR, or two merged into one preprod deploy): `make preprod-deploy ref=origin/<branch>`, human steps 1-4.
5. Part 4 PR: `make preprod-deploy ref=origin/<branch>`, then `STRELITZIA_AUTH_MODE=proxy` and
   `STRELITZIA_SITE_HEADER_URL=/shared/site-header.js` in `~/.strelitzia-preprod/.env` and `make preprod-strelitzia-up`.
   Human steps 5-10.
6. **Prod (user's go-ahead):** prod `.env` as in step 2 with a different secret, merge both engineerfamily PRs,
   `make tag-prod v=1.3.0`, `make deploy-prod ref=v1.3.0` (site sign-in on, dashboard still on its own flow), check
   steps 1-4 on prod, then the two settings from step 5 in `~/.strelitzia/.env` and `make strelitzia-up`. Everyone signs
   in once more (the old `strelitzia_session` no longer counts). Then the branding change from step 1.
7. **After a week without trouble (user):** remove the two `/strelitzia/dashboard/api/auth/callback` URIs from the client.
**Rollback** (reverse order, no data to undo: nothing here migrates the DB):
- Dashboard: delete `STRELITZIA_AUTH_MODE` and `STRELITZIA_SITE_HEADER_URL` from the `.env`, `make strelitzia-up` (or
  `preprod-strelitzia-up`) → the built-in Google flow and today's header are back. Do this **before** rolling back nginx or Flask, or the dashboard loses its identity.
- Site: `make deploy-prod ref=v1.2.0` (the tag before this work); preprod: `make preprod-deploy ref=origin/main`.
- Everyone signed out at once: rotate `SITE_SESSION_SECRET` and restart `app`.
**Validate:** each step's human checks below pass before the next step starts.
**Status:** 🟡 2026-10-19: steps 1-5 done on preprod. Preprod `/auth/verify` → 404, the spoofed `X-Auth-Request-Email` → `"user": null`
in proxy mode, and the `strelitzia-preprod` 301s are right. Human steps 1-10 pass (9 skipped). `make preprod-strelitzia-up` didn't recreate the
container after a change to the `.env` alone, so the dashboard stayed in `google` mode. #36 (fc08176) adds `--force-recreate` to the
`*strelitzia-up` targets; until #36 merges, run it from the PR branch or recreate by hand. Steps 6-7 are the user's (M31-M33).

## Validation
- Task 1-2 validations pass. Outside checks through Cloudflare after each deploy:
  `curl -s -o /dev/null -w "%{http_code}" https://engineerfamily.net/` → 200,
  `curl -s https://engineerfamily.net/auth/me` → `"signed_in": false`, `curl -s -o /dev/null -w "%{http_code}" https://engineerfamily.net/auth/verify` → 404,
  `curl -s -H 'X-Auth-Request-Email: <owner email>' https://engineerfamily.net/strelitzia/dashboard/api/auth/me` → `"user": null` (the spoofed header is dropped).

## Human test steps (preprod)
Browser: only the dev test account (owner on preprod), in its own profile; basic auth first, as today.
1. `https://preprod.engineerfamily.net/`: the engineerfamily home link top left, "Sign in" top right. Click it, pick the
   test account → back on `/`, its initials and a Sign out button top right.
2. `/games/`, `/strelitzia/` and `/strelitzia/privacy`: still signed in; the home link and the profile control look the same
   and sit in the same spots as on `/` (compare screenshots); the home link goes back to `/` from each.
3. "Sign out" → "Sign in" shows everywhere. Pages stay readable signed out. Repeat 1-2 at phone width (390 px).
4. DevTools → Application → Cookies: one `ef_session` with Path `/`, no Domain (host `preprod.engineerfamily.net`), HttpOnly, Secure, Lax.
5. (After step 5 of the rollout.) Signed in on `/`, open `/strelitzia/dashboard/` → the jobs table with no second Google
   prompt, the same home link top left and the same initials and Sign out top right as on `/`. The home link leads to `/`.
6. Users page (owner-only) loads; the Claude setup page's Connect Google Drive still reaches Google and comes back connected.
7. Sign out from the dashboard → signed out on `/` too; the dashboard shows its sign-in card under the same top bar;
   "Sign in with Google" returns to the dashboard.
8. `https://strelitzia-preprod.engineerfamily.net/strelitzia/dashboard/` → 301 to `preprod.engineerfamily.net`.
9. (User, optional, any Google account not invited on preprod.) Sign in on `/` → fine; the dashboard shows "isn't invited"
   with that email, "Use another account", and the home link and Sign out in its top bar.
10. Dashboard at phone width: home link first and profile last on the top row; the nav scrolls.
On prod, repeat 1-7 with the test account as an invited non-owner (step 6: Users page answers "owner only"). After the
branding change, the Google prompt says "engineerfamily".

## Decisions
1. Site sign-in and the header (parts 1-2) ship before the nginx cutover (this part), with separate env flags, so site sign-in can go live before the dashboard
   depends on it, and each step rolls back on its own.
2. Old dashboard callback URIs stay registered for a week: they're what the rollback needs.
3. `strelitzia-preprod.*` 301s instead of getting its own cookie, matching prod's `strelitzia.*` 301.
