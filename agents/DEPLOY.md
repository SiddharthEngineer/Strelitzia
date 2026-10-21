# Deploys (VPS)

Strelitzia runs inside the engineerfamily Docker stack (`SiddharthEngineer/engineerfamily`) as the compose service `strelitzia`,
served at `https://engineerfamily.net/strelitzia/dashboard/` (the static homepage is `/strelitzia/`). The old hosts
`strelitzia.engineerfamily.net` and `applypilot.engineerfamily.net` 301 to `engineerfamily.net/strelitzia/`, and their `/app/...`
to `/strelitzia/dashboard/...`. The dashboard used to live at `/app/` (until 2026-10).
Postgres runs in the compose service `postgres-db` (formerly `analytics-db`), which holds the DBs
`strelitzia` / `strelitzia_test` (prod) and `strelitzia_preprod` (preprod), owned by the role `strelitzia`, with passwords in the
engineerfamily `.env` keys `STRELITZIA_DB_PASSWORD*`. Until 2026-10 they were all named `applypilot`;
`services/nginx/.htpasswd-applypilot` keeps its old name.
For running a deploy step by step, Claude has the `engineerfamily-deploy` skill (`~/.claude/skills/`).

## Layout
| Path | Role |
|---|---|
| `~/src/Strelitzia` | Dev clone (`AGENT_REPO`). All edits, branches and commits happen here; unattended agents work in worktrees under `~/.local/state/agent-runner/worktrees/strelitzia/`. Nothing builds from it. |
| `~/src/engineerfamily` | engineerfamily dev clone (`main`). Commit here. |
| `/srv/Strelitzia-prod` | Prod build context, detached at a trunk commit. Moved only by `make strelitzia-deploy`; never edited by hand. It has no `.env`: the dashboard reads `~/.strelitzia/.env` through its `~/.strelitzia` mount. |
| `/srv/Strelitzia-preprod` | Preprod build context, moved to a review PR's head by `agent-runner preprod`. |
| `/srv/engineerfamily-prod` | prod checkout (branch `prod`, compose project `engineerfamily`). |
| `/srv/engineerfamily-preprod` | preprod checkout (compose project `engineerfamily-preprod`, port 8080). |

The old `/srv/ApplyPilot-*`, `~/.applypilot*` and `*/applypilot-agent` paths are gone (2026-10-13): nothing uses them and DB rows
hold `/home/dev/.strelitzia/...` paths.
`/srv` checkouts are `deploy:srv`, setgid, group-writable (`core.sharedRepository=group`), so nothing ever needs `chown`. git needs
each real path in `safe.directory` (`git config --global --get-all safe.directory`); the symlinked old path doesn't count.
Compose project names are pinned (`-p` and `COMPOSE_PROJECT_NAME`), so renaming a checkout never changes volume names.
Untracked server files (`.env`, `services/nginx/ssl/`, `.htpasswd*`) exist only in the `/srv` checkouts and are never committed.

## How a change reaches each environment
| Change | Preprod | Prod (the user approves each one) |
|---|---|---|
| Strelitzia (this repo) | Review PRs only: `agent-runner preprod` deploys the PR head (see below). Low-risk PRs auto-merge and skip preprod. | `make -C ~/src/engineerfamily strelitzia-deploy [ref=<sha>]`: moves `/srv/Strelitzia-prod` to `origin/trunk` (or `ref`) and rebuilds only the dashboard. |
| engineerfamily | `make -C ~/src/engineerfamily preprod-deploy [ref=<sha\|origin/branch>]`, no tag needed | Merge to `main`, then `make tag-prod v=X.Y.Z` and `make deploy-prod ref=vX.Y.Z` |

Prod tagging alone deploys nothing: `make deploy-prod ref=<tag>` dispatches engineerfamily's `deploy.yml` workflow, which resets the
`prod` branch to the tag and SSHes to the locked-down `deploy` account to rebuild the stack (`scripts/vps/engineerfamily-deploy`).

Every prod and preprod `make` target in engineerfamily acts on the `/srv` checkouts wherever it's run from. So `make ps`, `make logs`
and `make up` from `~/src/engineerfamily` operate on what's deployed, never on the dev tree. `make local-up` runs the dev tree.
`make up` and `make preprod-up` restart the whole stack. Prefer the narrow `strelitzia-*` targets (the `applypilot-*` names are deprecated aliases).

## Prod checks
Check from outside, through Cloudflare. A loopback check doesn't prove the hostname routes to the right nginx.
1. `https://engineerfamily.net`, `https://umami.engineerfamily.net`, `https://engineerfamily.net/strelitzia/` and
   `https://engineerfamily.net/strelitzia/dashboard/api/health` return 200, and `https://strelitzia.engineerfamily.net/app/` returns 301.
2. If one doesn't: for Strelitzia, run `make -C ~/src/engineerfamily strelitzia-deploy ref=<previous sha>`. For engineerfamily, run `make deploy-prod ref=<previous tag>`.

## Preprod (review PRs)
`agent-runner preprod` holds one lock for every repo: `deploy strelitzia <pr>` checks the PR head out in `/srv/Strelitzia-preprod`, runs
`make -C /srv/engineerfamily-preprod preprod-strelitzia-up`, and health-checks `https://preprod.engineerfamily.net/strelitzia/dashboard/api/health`
through Cloudflare (the netrc is in `~/.config/agent-runner/`). Merging or closing the PR frees the lock, and the next tick resets preprod to trunk.
Test at `https://preprod.engineerfamily.net/strelitzia/dashboard/` (or the same path on `strelitzia-preprod.engineerfamily.net`)
with the preprod login.
These preprod commands (app dir, deploy, seed, health check) come from the `[preprod]` section of `agents/runner.toml`.
Preprod uses its own disposable `strelitzia_preprod` DB (preprod postgres-db) and app dir (`~/.strelitzia-preprod`), never prod data.
**Preprod data is wiped and reseeded on every deploy** (a PR deploy or the reset to trunk): after the deploy command, the runner runs
the `[preprod] seed` command, which runs `scripts/seed_preprod.py` in a one-off container of the preprod image with the checkout mounted at `/seed`.
It leaves 18 fake jobs across every pipeline stage and user status, and refuses any DB not named exactly `strelitzia_preprod`
(or `applypilot_preprod`, its name before the rename).
A PR branched before the script existed deploys with `seed skipped` in `runs.log`.
```
PREPROD_SEED_CMD="docker compose -p engineerfamily-preprod --project-directory /srv/engineerfamily-preprod -f /srv/engineerfamily-preprod/docker-compose.base.yml -f /srv/engineerfamily-preprod/docker-compose.preprod.yml run --rm --no-deps -T -v /srv/Strelitzia-preprod:/seed:ro strelitzia python /seed/scripts/seed_preprod.py"
```
It has **no `.env` and no LLM keys, on purpose** (user, 2026-10-12): score and tailor actions fail there with a missing-key error. Don't add one.

## Google sign-in
Dashboard login (`src/strelitzia/web/auth.py`) is **off until `STRELITZIA_GOOGLE_CLIENT_ID` is set**: without it every
request acts as the owner, as before accounts existed, so merging or deploying sign-in never locks anyone out.
To turn it on for an environment, the user (secrets are never handled by an agent) adds to that environment's `.env`
(`~/.strelitzia/.env` for prod, `~/.strelitzia-preprod/.env` for preprod):
- `STRELITZIA_GOOGLE_CLIENT_ID`, `STRELITZIA_GOOGLE_CLIENT_SECRET`: a Google OAuth client of type Web application.
- `STRELITZIA_SESSION_SECRET`: a long random string (e.g. `openssl rand -hex 32`). Changing it signs everyone out
  (it's also the only way to revoke a session early, besides disabling the account).
- `STRELITZIA_OWNER_EMAIL`: the owner's Google email. An owner row still called `owner@localhost` is re-keyed to it on
  the owner's first sign-in.
- `STRELITZIA_PUBLIC_URL`: the bare origin the browser uses, with no path: `https://engineerfamily.net` (prod) or
  `https://preprod.engineerfamily.net` (preprod). The app appends `/strelitzia/dashboard/api/...` itself for the OAuth
  redirect URIs. An https URL makes the session cookie `Secure`.

With the client id set, the app refuses to start unless the client secret, session secret and owner email are set too.

Authorized redirect URIs on the OAuth client (the user adds them; see Google Cloud below):
- `https://engineerfamily.net/auth/callback` and `https://preprod.engineerfamily.net/auth/callback`: engineerfamily's
  site-wide sign-in, which the dashboard trusts in proxy mode.
- `https://engineerfamily.net/strelitzia/dashboard/api/drive/callback` and the same path on `preprod.engineerfamily.net`.
- The dashboard's own `.../strelitzia/dashboard/api/auth/callback` URIs on prod and preprod were removed on 2026-10-19
  (M33): proxy mode doesn't use them. Rolling back to `google` mode there means adding them again first.
- `http://localhost:8765/strelitzia/dashboard/api/auth/callback` and `.../strelitzia/dashboard/api/drive/callback`, for local
  `strelitzia serve` with `STRELITZIA_PUBLIC_URL=http://localhost:8765`. Not known to be set: ask the user to add them before testing login locally.

The old `https://strelitzia(-preprod).engineerfamily.net/app/api/...` pairs can be removed once nothing runs the `/app` build.

### Sign-in modes (`STRELITZIA_AUTH_MODE`)
`auth.auth_mode()` picks one of three; `GET /strelitzia/dashboard/api/auth/me` reports it as `mode`.
- **off**: no client id and no `STRELITZIA_AUTH_MODE`. Every request acts as the owner.
- **google**: `STRELITZIA_GOOGLE_CLIENT_ID` is set. The built-in Google flow above (self-hosters without a proxy, and
  the rollback path for site-wide sign-in).
- **proxy**: `STRELITZIA_AUTH_MODE=proxy` (wins over the client id). The dashboard runs no sign-in of its own: the
  reverse proxy (engineerfamily's nginx `auth_request`, or oauth2-proxy) signs the visitor in and passes two headers:
  `X-Auth-Request-Email` (required) and `X-Auth-Request-Preferred-Username` (display name, percent-encoded). The invite
  list, the owner (and its `owner@localhost` re-key), disabled accounts and admin routes work as in google mode; an
  uninvited or disabled email gets 401 with `not_invited` / `disabled`, and the sign-in screen names the account and
  offers "Use another account". Needs `STRELITZIA_OWNER_EMAIL` and `STRELITZIA_SESSION_SECRET` (Drive connect's state);
  Drive connect also needs the Google client id and secret, as before.
  - `STRELITZIA_SITE_LOGIN_URL` (default `/auth/login`): where the dashboard's Sign in goes, with `?next=/strelitzia/dashboard/`.
  - `STRELITZIA_SITE_LOGOUT_URL` (default `/auth/logout`): what Sign out POSTs (the site's session, not the dashboard's).
  - **Proxy mode is safe only when nothing but the proxy can reach the container**: the headers are the whole proof
    of identity, and anyone who can talk to the app directly can set them. On the VPS: no published port, and part 4
    (`site-sso-4-cutover`) moves the container off the shared `web` network. The headers are ignored in the other modes.

`STRELITZIA_SITE_HEADER_URL` (any mode, e.g. `/shared/site-header.js`): engineerfamily's shared header script. When set,
the dashboard's top bar starts with `<ef-home>` and ends with `<ef-profile>`. In proxy mode `<ef-profile>` carries Sign
out and replaces the dashboard's own user menu; in google mode the user menu stays (its session is the dashboard's).
Unset, a self-hosted dashboard keeps its own header.

### Google Drive per user
Each user connects their own Drive on the Claude setup page (**Connect Google Drive**, scope `drive.file` only, a
separate consent after sign-in). It needs login on and `STRELITZIA_TOKEN_KEY`, a Fernet key
(`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`) that encrypts the tokens
in the `user_drive` table. Without the key (or with login off) the dashboard can't connect Drive, and the owner keeps
using the CLI's `google_token.json`. With the key set, the next start imports that file into the owner's row once (the
file stays). Disconnect revokes the token at Google and deletes the row. The CLI has no Drive commands any more
(user-auth-8-cli), so `google_token.json` can't be created afresh: a new install connects Drive from the dashboard.
Changing the key makes the stored tokens unreadable: everyone connects again. The web client must be in the same
Google Cloud project as the Drive desktop client, since `drive.file` only sees files that project created.

With login on, every `/strelitzia/dashboard/api/*` route except `/strelitzia/dashboard/api/health` and
`/strelitzia/dashboard/api/auth/*` returns 401 without a session
(30 days, `HttpOnly`, `SameSite=Lax`); the UI routes stay public. Only the owner and invited emails get in; anyone else
lands on `/strelitzia/dashboard/?auth=not_invited`. The resume workbench (packet, result, Claude setup) stays owner-only until per-user
content libraries (#48) exist: it reads the owner's resume (Drive is per user, below). nginx basic auth is gone on prod
(engineerfamily #31, 2026-10-18), so Google sign-in is prod's only gate; preprod keeps basic auth in front until
engineerfamily E2 (preprod-open) removes it.
Preprod's no-`.env` rule above is about LLM keys: an auth-only `.env` there is the user's call.

### Google Cloud project (set up by hand)
The user did all of this in the Google Cloud Console between 2026-10-05 and 2026-10-17. Agents can't see the Console, so
this section is the record of what's there. Change anything in the Console only through the user, and update this section
when they do. The project and client facts below were checked on 2026-10-18 from the client ids in the `.env` files and
`google_client_secret.json`; the Console settings are as the user reported them.

- **Project:** display name "Engineer Xmas List", ID `engineer-xmas-list`, number `952717433799`. It's an older project
  reused for Strelitzia; IDs can't be renamed. **Stay in this project.** `drive.file` only lets an app see files created by
  clients of the same project, so a client in another project couldn't see existing Drive folders and files and would
  create duplicates. A second, unused project named "Strelitzia" was made by mistake on 2026-10-13; nothing references it.
  Whether it was deleted is unconfirmed.
- **Google Auth Platform → Branding:** app name `engineerfamily` (2026-10-19, M32, as the user reported; it was `Strelitzia`
  from 2026-10-13), since sign-in is now site-wide. Home page `https://engineerfamily.net/`, privacy policy
  `https://engineerfamily.net/privacy` (served by engineerfamily's Flask app; keep both URLs answering 200). Authorized domain `engineerfamily.net`,
  which covers every subdomain. **No logo:** uploading one triggers Google's brand verification.
- **Data access (scopes):** `openid`, `.../auth/userinfo.email`, `.../auth/userinfo.profile`, `.../auth/drive.file`. All four
  are non-sensitive, so the app needs no Google verification. Adding a sensitive or restricted scope (full `drive`, Gmail,
  and so on) would require verification: don't add one without the user deciding to.
- **Audience:** External, **published (In production)**. In Testing mode, refresh tokens expire after 7 days and only
  listed test users can sign in. The app is unverified, so users see "Google hasn't verified this app" and continue through
  **Advanced**. Who gets in is decided by the app's invite list (owner + invited emails), not by Google.
- **Clients**, both in this project:
  - **Desktop (installed) client** from 2026-10-05: `~/.strelitzia/google_client_secret.json`. The old CLI Drive sync used it;
    `~/.strelitzia/google_token.json` came from it and was imported into the owner's `user_drive` row. Ask before
    deleting it in the Console: Drive files it created stay visible to the web client either way (same project).
  - **Web client "Strelitzia web"** (2026-10-17): its id and secret are `STRELITZIA_GOOGLE_CLIENT_ID` / `_SECRET`. **Prod and
    preprod share this one client**, with the https redirect URIs above.
- **`.env` (user-managed):** prod and preprod each have their own `STRELITZIA_SESSION_SECRET` and `STRELITZIA_TOKEN_KEY`.
  `STRELITZIA_OWNER_EMAIL` is the user's own Google account on prod and the dev test account on preprod (2026-10-18).
  Each `.env` needs its **own** `STRELITZIA_PUBLIC_URL`: until 2026-10-18 preprod's pointed at prod, so preprod sign-in
  bounced to `strelitzia.engineerfamily.net`. Nginx basic auth on preprod does not break sign-in (the browser resends its
  cached credentials on the callback).
- **Sign-in works on prod** (M25/M27, 2026-10-17/18).
- **Test account** (2026-10-18): a separate Google account for agents' browser testing (address in the user's notes and
  preprod's `STRELITZIA_OWNER_EMAIL`, not in this public repo). It is the **owner on preprod** (so owner-only pages such as
  the resume workbench and `/claude-setup` can be tested; preprod data is fake) and an **invited non-owner on prod**.
  The user signs it in once in a dedicated browser profile (sessions last 30 days); agents drive that profile and never
  hold its password or 2FA. Never sign in to any environment with the user's own account.
