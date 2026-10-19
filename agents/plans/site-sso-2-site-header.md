# Plan: Site-wide sign-in, part 2: one header contract (home link top left, profile top right)
**Status:** ❌ Not started
**Risk:** review (user-facing on every page; lands in the engineerfamily repo)
**Depends on:** site-sso-1-site-auth (`/auth/me`, `/auth/login`, `/auth/logout`)

## Goal
On every engineerfamily.net page (the homepage and games, Strelitzia's static pages, and the dashboard after part 3)
the header starts with the same engineerfamily home link in the top left, which always goes back to
`engineerfamily.net/`, and ends with the same sign-in / profile / sign-out control in the top right. Each looks,
sits and behaves identically everywhere; only the app's own brand and nav between them differ.

## Context
- Three headers today, three stylesheets: `~/src/engineerfamily/services/app/vite/src/App.jsx:3-28` + `styles.css:35-80`
  (pill `site-nav`, `brand-link`), `~/src/engineerfamily/services/strelitzia/index.html:13-16` + `style.css:18-19`
  (`header a.brand`), and the dashboard's `.topbar` (`dashboard/src/App.tsx:46-69`, `dashboard/src/styles.css:63-64`, part 3).
- `/auth/me` → `{enabled, signed_in, email, name}` (part 1). When `enabled` is false the control renders nothing.
- Gotchas: the two pieces must not inherit page CSS (three different themes), so they are custom elements with Shadow
  DOM and their own fixed styles (font stack, sizes, colors from their own CSS custom properties, light and dark via
  `prefers-color-scheme`). One `customElements.define` guard so loading the script twice is harmless.
  The script is same-origin and has no build step, so the static pages, the Vite app and the dashboard can all load it.

## Tasks
### Task 1: the shared header script
**Runs:** interactive (engineerfamily repo)
**Files:** `services/shared/site-header.js` (new), `services/shared/README.md` (new),
`services/nginx/nginx.prod.conf`, `services/nginx/nginx.preprod.conf` (modify: `location /shared/` serves the folder,
mounted into nginx in `docker-compose.base.yml`; `Cache-Control: no-cache` so a change shows at once)
**What:** two custom elements.
- `<ef-home>`: the engineerfamily wordmark, a link to `/`, fixed size and padding, the first thing in every header.
- `<ef-profile next="<path>">`: fetches `/auth/me` once. Signed out: a "Sign in" button to `/auth/login?next=<path>`
  (`next` defaults to the current path). Signed in: a round initials button (no Google picture: no third-party image loads)
  followed by a visible **Sign out** button (`POST /auth/logout`, then reload; the user wants a real button, 2026-10-18).
  The initials open a small menu with the name, email and a "Strelitzia dashboard" link. Keyboard: Enter/Space opens,
  Escape closes, focus returns to the button. The last thing in every header.
README: the contract (both elements, where they go, that pages must not restyle them).
**Validate:** `node --check services/shared/site-header.js` → exit 0; `nginx -t` (repo rules) → ok for both envs;
after a preprod deploy `curl -s -u <creds> -o /dev/null -w "%{http_code}" https://preprod.engineerfamily.net/shared/site-header.js` → 200.
**Status:** ❌

### Task 2: use it on the site and Strelitzia's static pages
**Runs:** interactive (engineerfamily repo; checked in a browser on preprod)
**Files:** `services/app/vite/index.html`, `services/app/vite/src/App.jsx`, `services/app/vite/src/styles.css`,
`services/strelitzia/index.html`, `services/strelitzia/privacy.html` (modify)
**What:** load `/shared/site-header.js` in each page's `<head>`. Site header: `<ef-home>`, then the nav (Games,
Strelitzia), then `<ef-profile>` pushed right; the old `brand-link` goes (the home link is `<ef-home>` now).
Strelitzia static header: `<ef-home>`, then the Strelitzia brand and nav, then `<ef-profile>`. At phone width the nav
may wrap or scroll, but `<ef-home>` stays first and `<ef-profile>` stays last on the top row.
**Validate:** `npm --prefix services/app/vite run build` → succeeds; `grep -c "ef-home\|ef-profile" services/strelitzia/*.html` → 2 per page.
**Status:** ❌

## Validation
- Task validations pass. Preprod: the human steps in `site-sso-4-cutover` (1-4, then 5 and 10 for the dashboard).

## Human test steps (preprod)
See `site-sso-4-cutover`, steps 1-4.

## Decisions
1. Shared custom elements with Shadow DOM instead of three copies of the same CSS: the user wants the home link and the
   profile control identical everywhere (2026-10-18), and three hand-kept copies would drift.
2. engineerfamily serves the script (`/shared/`); Strelitzia only loads it when told to (part 3), so a self-hosted
   Strelitzia without engineerfamily keeps its own header.
3. This covers the home-link and profile parts of the "Shared header" backlog item; restyling the nav itself to match
   stays in the backlog.
