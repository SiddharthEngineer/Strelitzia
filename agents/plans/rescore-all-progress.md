# Plan: the Jobs page shows a running Rescore all again after a reload
**Status:** 🟡 code done 2026-10-26, preprod test pending
**Risk:** review (dashboard UI; `dashboard/*` is high-risk in `agents/runner.toml`, so the PR needs a human)
**Depends on:** none

## Goal
On 2026-10-26 the user ran Rescore all on prod and thought it failed. It worked: task `rescore_all` ran 16:27–16:34 UTC
and assessed 20 of 21 jobs (one not extracted), 0 errors. But the progress banner lives only in `JobsPage` state, so
it disappeared when the user reloaded the page or opened a job and came back during the batch. The button looked
available again and the list didn't refresh when the batch finished. After this change, opening the Jobs page while a
Rescore all is queued or running shows its banner, keeps the button disabled, and reloads the list when it's done.

## Context
- `src/strelitzia/web/tasks.py`: `active_task(conn, user_id, kind)` finds the user's queued or running all-jobs task;
  `POST /rescore` already uses it to refuse a second paid run.
- `dashboard/src/pages/JobsPage.tsx`: `rescoreTask` state feeds `<TaskProgress>`, which polls `GET /tasks/{id}` every 3 s.
- A Rescore all queued from the Preferences page (`reassess_scope: "active"`) is the same kind and shows too.

## Tasks
### Task 1: endpoint, page and tests
**Runs:** interactive
**Files:** src/strelitzia/web/app.py, dashboard/src/api.ts, dashboard/src/pages/JobsPage.tsx, tests/web/test_preferences_api.py,
dashboard/src/__tests__/{JobsTable,Workspace,api}.test.ts(x), src/strelitzia/web/static/* (rebuilt)
**What:** `GET /rescore/active` returns `{"task": <the user's queued or running rescore_all> | null}`. `JobsPage` calls
it on mount and, if a task comes back and none is shown yet, sets `rescoreTask`. Tests: the endpoint (none, another
user's, queued, running, done); the page restores the banner, disables the button and reloads the list on done; no
banner when nothing runs; the API client URL.
**Validate:** `scripts/validate.sh --full` passes.
**Status:** 🟡 code done 2026-10-26

## Human test steps (preprod)
1. As the dev test account, open `https://preprod.engineerfamily.net/strelitzia/dashboard/` and click **Rescore all**,
   then **Re-assess** (a few cents on Batch). The banner says it's queued or running and the button is disabled.
2. Reload the page: the banner is back and the button is still disabled.
3. Open a job, then go back to Jobs: the banner is still there.
4. When the batch finishes (minutes, up to an hour), the banner says it finished, the list reloads and the button is enabled.
5. Reload once more: no banner.
