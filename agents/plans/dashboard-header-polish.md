# Plan: dashboard header polish at phone width and when signed out (R43 follow-up)
**Status:** ❌ Not started
**Risk:** review (dashboard UI; `dashboard/*` is high-risk in `agents/runner.toml`, so the PR needs a human)
**Depends on:** - (engineerfamily E1 [header-fit](https://github.com/SiddharthEngineer/engineerfamily/blob/main/agents/plans/done/header-fit.md) fixed the static pages)

## Goal
Two small header problems found by the signed-in QC on preprod (2026-10-19, Claude in Chrome as the dev test account, preprod on
engineerfamily main 52a22f8). Every other header check passed at 1280, 500 and 390 px.
1. **Dashboard nav when narrow.** At ≤640 px the nav is its own row with `overflow-x: auto` and a hidden scrollbar. At 390 px it is
   216 px wide (scrollWidth 532), so only Jobs, Contacts and Profile show, plus a clipped sliver of "Preferences". Panel, Claude setup and
   Users can be reached only by swiping, and nothing shows that the row scrolls. At 500 px, 3 of 7 links are off-screen too.
2. **Signed-out card.** After Sign out from the dashboard (proxy mode), the page is only the "Sign in to see your jobs" card. The header
   above it was empty: no `<ef-home>` link back to engineerfamily (`document.querySelector('ef-profile')` was `null`), though
   `/strelitzia/dashboard/api/auth/me` answered with `site_header_url: "/shared/site-header.js"`. Signing in again worked.

## Context
- `dashboard/src/styles.css:327-345`: the ≤640 px grid for `.site-topbar` (`"home brand . profile" "nav nav nav add"`), the nav's
  `overflow-x: auto; scrollbar-width: none`.
- `dashboard/src/styles.css:213-216`: `.nav` and `.nav a.active`.
- `dashboard/src/pages/SignInPage.tsx`: renders `<header class="topbar site-topbar">` with `<SiteHome />` and `<SiteProfile />` only when
  `me?.site_header_url` is set, and calls `useSiteHeader`.
- `dashboard/src/App.tsx:19-33`: a 401 sets `signedOut` and refetches `/auth/me`; until that returns, `me` may be stale or `null`, so the
  header may render without `site_header_url`. The full-page load after `siteLogout` starts with `me = null` too.
- `dashboard/src/components/SiteSlots.tsx`: `useSiteHeader` adds the script once; `<ef-home>` and `<ef-profile>` render themselves.
- Signed out, `<ef-profile>` shows a "Sign in" control (engineerfamily `services/shared/site-header.js`).

## Tasks
### Task 1: the narrow nav shows that it scrolls
**Runs:** unattended
**Files:** dashboard/src/styles.css (modify), dashboard/src/App.tsx (modify, only for scrolling the active link into view)
**What:** At ≤640 px, show that the nav row scrolls: e.g. a fade on the edge that has more links (`mask-image`, or scroll-driven
shadows), and on route change scroll the active link into view (`scrollIntoView({ inline: 'nearest', block: 'nearest' })`), so a page
like Users never has its own tab hidden. Alternatively let the links wrap onto a second line if that reads better; pick one and record it
in Decisions. Don't change the ≥641 px layout.
**Validate:** `scripts/validate.sh` passes. Dashboard tests pass. On a local build at 390 px: the clipped edge is visibly faded, and
opening `/users` scrolls "Users" into view.
**Status:** ❌

### Task 2: the signed-out page keeps the site header
**Runs:** unattended
**Files:** dashboard/src/pages/SignInPage.tsx (modify), dashboard/src/App.tsx (modify, if the cause is there),
dashboard/src/__tests__/SignInPage.test.tsx (modify)
**What:** Find why the header is empty after Sign out in proxy mode (likely `me` is `null` or stale when `SignInPage` first renders and
the header isn't shown or the script isn't loaded once it arrives). Fix it so that, signed out in proxy mode, the page shows
`<ef-home>` (link to engineerfamily) and `<ef-profile>` (Sign in) above the card. Add a test: `SignInPage` with a `me` that has
`site_header_url` renders both slots, and the header appears when `me` arrives after the first render.
**Validate:** `scripts/validate.sh` passes. Dashboard tests pass, including the new one.
**Status:** ❌

### Task 3: tracking
**Runs:** unattended
**Files:** agents/ROADMAP.md (modify)
**What:** Set R46's status to ✅ with the PR number.
**Validate:** `scripts/validate.sh` passes.
**Status:** ❌

## Validation
- `scripts/validate.sh` passes; CI is green.

## Human test steps (preprod)
1. As the dev test account, open `https://preprod.engineerfamily.net/strelitzia/dashboard/` in a phone-width window (or a 390 px
   iframe; Chrome windows stop at 500 px): the nav row shows a fade where links are hidden, and Users/Claude setup open and stay visible.
2. Sign out from the dashboard: the engineerfamily home link and a Sign in control are at the top, above the card.
3. Sign in again: you land back on the dashboard as the test account.

## Decisions
1. Split from engineerfamily E1 because both fixes are in the Strelitzia dashboard (2026-10-19, user asked to save them for later).
