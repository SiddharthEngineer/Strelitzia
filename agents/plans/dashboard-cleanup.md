# Plan: Dashboard cleanup (issue #98, items 1, 4, 5, 6)
**Status:** ❌ Not started (planned with the user 2026-10-27)
**Risk:** low (dashboard UI and one sort key; no data changes)
**Depends on:** —

## Goal
Four small fixes from #98: no Users link in the dashboard's nav, no "Added by me / Discovered" filter, the Jobs list
sorted by status then fit score by default, and a clear warning before Set up Profile Docs overwrites the Docs.
(#98 item 2 is engineerfamily's E14; item 3 is [job-edit-delete](job-edit-delete.md).)

## Context
- `dashboard/src/App.tsx:42-43,93`: site admins get a "Users" link to engineerfamily's `/users/`. The site header's
  account menu already has the same link (`engineerfamily services/shared/site-header.js`), so it's a duplicate.
  `me.site_admin` / `me.users_url` come from `web/auth.py`.
- `dashboard/src/components/Filters.tsx:7,84` (`SOURCE_OPTIONS`), `dashboard/src/pages/JobsPage.tsx:36,56,165` (the
  "Added by me" default that depends on facets), `src/strelitzia/web/queries.py:26,36,115-116,213-225` (`source`
  filter and facet). Jobs come in by manual upload from now on, so the filter splits nothing.
- Sorting: `queries.py:18-24` `SORT_COLUMNS`, `:124-130` `order_clause` (one key + `url`);
  `web/app.py:91` default `-discovered_at`; `dashboard/src/useQueryState.ts:7` `DEFAULT_SORT`.
  The shown status is computed (`tracking.effective_status`: `user_status`, `apply_status`, deadline), so sorting on it
  needs a SQL `CASE` that mirrors it. `where_clause`'s status filter already has SQL for each status: reuse it.
- `dashboard/src/pages/ClaudeSetupPage.tsx:115-126`: the overwrite prompt is a plain `.notice`. What overwrite really
  does (`profile_sync.setup_profile_docs`): rewrites both Docs with the app's **last-synced copy**, or the example
  templates where that copy is empty. Edits made in the Docs since the last sync are lost.

## Tasks
### Task 1: Remove the Users link
**Runs:** unattended
**Files:** dashboard/src/App.tsx (modify), dashboard/src/__tests__/SiteSlots.test.tsx (modify)
**What:** Drop `usersUrl` and the nav link. Leave `site_admin`/`users_url` in `/me` (harmless; other callers may use
them) and leave `web/admin.py` (standalone `strelitzia serve` without engineerfamily still uses it).
**Validate:** `cd dashboard && npm test -- SiteSlots` → no "Users" link for a site admin.
**Status:** ❌

### Task 2: Remove the source filter
**Runs:** unattended
**Files:** dashboard/src/components/Filters.tsx, dashboard/src/pages/JobsPage.tsx, dashboard/src/useQueryState.ts,
dashboard/src/types.ts, src/strelitzia/web/queries.py, src/strelitzia/web/app.py (modify); their tests
**What:** Remove the source buttons, the "Added by me" default and the facet. The API ignores a stale `source=` query
param (old bookmarks) instead of 422. Keep the `source` column and the "manual" value on new rows.
**Validate:** `pytest tests/test_web_jobs.py -q` and `npm test -- JobsPage` → list shows every job, no source facet.
**Status:** ❌

### Task 3: Default sort = status, then fit score
**Runs:** unattended
**Files:** src/strelitzia/web/queries.py, src/strelitzia/web/app.py, dashboard/src/useQueryState.ts,
dashboard/src/components/JobsTable.tsx (modify); tests
**What:** New sort key `status` = a `CASE` rank of the effective status, then `fit_score DESC NULLS LAST`, then `url`.
Rank (decision 1): heard_back, in_progress, submitted, active, inactive, rejected. Make it the default in the API and
`DEFAULT_SORT`; clicking a column header still sorts by that column alone, and the Status header sorts by `status`.
**Validate:** `pytest tests/test_queries.py -q` → the rank matches `effective_status` for each fixture row (one test
per status, including deadline-driven active/inactive), and ties order by fit score.
**Status:** ❌

### Task 4: Overwrite warning
**Runs:** unattended
**Files:** dashboard/src/pages/ClaudeSetupPage.tsx, dashboard/src/styles.css (modify); its test
**What:** Show the prompt as a warning box (Sunrise theme's warning/orange tokens; add a `.notice.warning` class if
none exists) with: "**This replaces the text of {docs}.** They'll be rewritten from the app's last-synced copy (the
example templates where that copy is empty). Edits you made in the Docs since the last sync ({relative time}) will be
lost. Use Sync now on the Profile page first to keep them." The button reads "Replace the Docs". The button that opens
the prompt also gets a one-line muted hint when Docs already exist.
**Validate:** `npm test -- ClaudeSetupPage` → the warning text and class render when setup returns `existing`.
**Status:** ❌

## Validation
- `scripts/validate.sh --full` passes.

## Human test steps (preprod)
1. As a site admin: the dashboard nav has no Users link; the account menu still has one.
2. Jobs page: no source filter; the list opens sorted by status, then fit score; clicking Fit sorts by fit only.
3. Claude setup → Set up Profile Docs with existing Docs → an orange warning that says what gets replaced.

## Decisions (proposed, confirm in review)
1. Status order for the default sort: heard_back, in_progress, submitted, active, inactive, rejected (live work first,
   closed last).
