# Plan: dashboard header: Users moves to the profile menu, the narrow nav shows it scrolls, the signed-out page keeps the site header
**Status:** ❌ Not started
**Risk:** review (dashboard UI; `dashboard/*` is high-risk in `agents/runner.toml`, so the PR needs a human)
**Depends on:** engineerfamily E3 [site-header-bar](https://github.com/SiddharthEngineer/engineerfamily/blob/main/agents/plans/site-header-bar.md)
(queue order: it puts Users and Sign out in `<ef-profile>`'s menu and turns `<ef-home>` into a home icon)

## Goal
The dashboard's top bar is now the house style for the whole site (user, 2026-10-22); its look and its own links stay as
they are. On engineerfamily.net (proxy mode) the shared `<ef-profile>` menu carries **Users** (for the owner) and
**Sign out**, so the dashboard drops its own **Users** nav link there; `<ef-home>` is a home icon now, so the ≤640 px grid
must still fit. Plus two problems the signed-in QC found on preprod (2026-10-19, at 390 and 500 px):
1. **Narrow nav.** At ≤640 px the nav is its own row with `overflow-x: auto` and a hidden scrollbar. At 390 px only Jobs,
   Contacts and Profile show, and nothing shows that the row scrolls.
2. **Signed-out card.** After Sign out (proxy mode) the page is only the "Sign in to see your jobs" card: no `<ef-home>`
   or `<ef-profile>` above it, though `/auth/me` answered with `site_header_url: "/shared/site-header.js"`.

## Context
- `dashboard/src/App.tsx:43-85`: `isOwner`, `site` (`me.site_header_url`), `siteSession` (`site && me.mode === 'proxy'`);
  the header renders `<SiteHome />`, brand, `nav` (… `{isOwner && <NavLink to="/users">Users</NavLink>}`), Add job,
  the own user menu with Sign out only when `!siteSession`, and `<SiteProfile />`. The `/users` route stays for the owner.
- `dashboard/src/__tests__/UsersPage.test.tsx:118-147`: "Users nav link" tests (owner sees it, others don't).
- `dashboard/src/styles.css:63` (`.topbar`), `:213-216` (`.nav`), `:327-345` (≤640 px grid for `.site-topbar`:
  `"home brand . profile" "nav nav nav add"`, nav `overflow-x: auto; scrollbar-width: none`). Don't change the ≥641 px look.
- `dashboard/src/pages/SignInPage.tsx`: renders `<header class="topbar site-topbar">` with the slots only when
  `me?.site_header_url` is set. `App.tsx:19-33`: a 401 sets `signedOut` and refetches `/auth/me`, so `me` may be `null` or
  stale on the first render; the full-page load after `siteLogout` starts with `me = null` too.
- `dashboard/src/components/SiteSlots.tsx`: `useSiteHeader` adds the script once.
- The bundle is committed: `npm run build --prefix dashboard` writes `src/strelitzia/web/static/`.

## Tasks
### Task 0: Users lives in the profile menu on engineerfamily.net
**Runs:** unattended
**Files:** dashboard/src/App.tsx (modify), dashboard/src/__tests__/UsersPage.test.tsx (modify)
**What:** Show the Users nav link only when `isOwner && !siteSession` (local or non-proxy runs keep it; in proxy mode the
site menu has it). Keep the `/users` route for the owner in both modes. Tests: owner in proxy mode (`mode: 'proxy'`,
`site_header_url` set) has no Users link in the Main nav and `/users` still renders the page; the existing owner/other tests
keep passing (they are non-proxy).
**Validate:** `npm test --prefix dashboard` passes; `scripts/validate.sh` passes.
**Status:** ✅ 2026-10-23 (this commit)

### Task 1: the narrow nav shows that it scrolls
**Runs:** unattended
**Files:** dashboard/src/styles.css (modify), dashboard/src/App.tsx (modify, only to scroll the active link into view)
**What:** At ≤640 px, show that the nav row scrolls: a fade on the edge that has more links (`mask-image`, or scroll-driven
shadows), and on route change scroll the active link into view (`scrollIntoView({ inline: 'nearest', block: 'nearest' })`).
Or let the links wrap onto a second line if that reads better; pick one and record it in Decisions. Check the top row
(home icon, brand, profile) still fits at 390 px. Don't change the ≥641 px layout.
**Validate:** `npm test --prefix dashboard` passes; `scripts/validate.sh` passes.
**Status:** ❌

### Task 2: the signed-out page keeps the site header
**Runs:** unattended
**Files:** dashboard/src/pages/SignInPage.tsx (modify), dashboard/src/App.tsx (modify, if the cause is there), dashboard/src/__tests__/SignInPage.test.tsx (modify)
**What:** Find why the header is empty after Sign out in proxy mode and fix it so the page shows `<ef-home>` and
`<ef-profile>` (Sign in) above the card. Test: `SignInPage` with a `me` that has `site_header_url` renders both slots, and
the header appears when `me` arrives after the first render.
**Validate:** `npm test --prefix dashboard` passes, including the new test; `scripts/validate.sh` passes.
**Status:** ❌

### Task 3: bundle and tracking
**Runs:** unattended
**Files:** src/strelitzia/web/static/index.html (modify), src/strelitzia/web/static/assets/* (regenerate), agents/ROADMAP.md (modify), agents/plans/dashboard-header-polish.md (modify)
**What:** `npm run build --prefix dashboard` and commit the bundle. Task statuses; R46's status to ✅ with the PR number.
**Validate:** `scripts/validate.sh --full` passes (includes "dashboard bundle committed").
**Status:** ❌

## Validation
- `scripts/validate.sh --full` passes; CI is green.

## Human test steps (preprod)
1. As the dev test account at 1280 px, open `https://preprod.engineerfamily.net/strelitzia/dashboard/`: the bar looks as
   before (white, rule, Jobs … Claude setup, Add job), with a home icon first that goes to `/`, and no Users link in the nav.
2. Open the avatar menu: Users and Sign out are there; Users opens `/strelitzia/dashboard/users` and the Users page shows.
3. At 390 px: home icon, brand and avatar share the top row; the nav row shows a fade (or wraps) where links are hidden;
   opening `/strelitzia/dashboard/claude-setup` keeps "Claude setup" visible in the nav.
4. Last: Sign out from the avatar menu: the home icon and a Sign in control are at the top, above the sign-in card.

## Decisions
1. Split from engineerfamily E1 because both fixes are in the dashboard (2026-10-19, user asked to save them for later).
2. 2026-10-22 (user): the dashboard's bar is the house style and keeps its own links; no restyle toward the static
   `/strelitzia/` page (that part of the 2026-10-19 plan is dropped). Users and Sign out live in the site profile menu.
