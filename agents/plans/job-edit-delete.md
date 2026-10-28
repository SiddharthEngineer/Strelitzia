# Plan: Edit or delete a job (issue #98, item 3)
**Status:** ✅ Complete 2026-10-28 (human test steps on preprod pending)
**Risk:** low (user, 2026-10-27: merge without a review wait; protected paths still get the automated review and preprod check; was review: deletes user data)
**Depends on:** —

## Goal
On the job page, the user can fix a job's details (title, company, location, work mode, salary, deadline) and delete a
job they no longer want, with everything that belongs to it.

## Context
- `src/strelitzia/web/app.py:225-243` `JobPatch` edits only `submitted_at` and `notes`; `:659` `PUT /jobs/{key}/description`
  already edits the description. Jobs are keyed by `(user_id, url)`; `job_key` makes the URL-safe key.
- Tables with `job_url` (`database.py`): `status_events`/`dashboard_tasks` (`:227`), `job_contacts` (`:250`),
  `interviews` (`:255`), `drafts` (`:263`), `panel_items` (`:277`, or the panel tables after R63). `llm_usage` keeps
  spend history and stays.
- Drive: each job has a folder (`jobs.drive_folder_id`, `storage/drive_layout.py`) with PDFs and the draft Docs.
- A fit score depends on title/description; changing them should mark the score stale (the Rescore button exists:
  `app.py:544`).

## Tasks
### Task 1: Edit fields API
**Runs:** unattended
**Files:** src/strelitzia/web/app.py (modify), tests/test_web_jobs.py (modify)
**What:** Extend `JobPatch` with `title`, `company`, `location`, `work_mode`, `salary`, `deadline` (only fields present
change; empty title/company → 422). Editing title or company sets a `score_stale` flag in the detail so the page offers
Rescore. The URL is not editable (decision 1).
**Validate:** `pytest tests/test_web_jobs.py -q -k patch` → each field saves; another user's job → 404.
**Status:** ✅ 2026-10-28 (0d5939f)

### Task 2: Delete API
**Runs:** unattended
**Files:** src/strelitzia/tracking.py or src/strelitzia/database.py (add `delete_job`), src/strelitzia/web/app.py
(modify), tests/test_web_jobs.py (modify)
**What:** `DELETE /jobs/{key}` removes the job row and its rows in every table above in one transaction, scoped by
`user_id`. Contacts themselves stay (they are shared across jobs); only the link goes. Running tasks for the job are
cancelled first. The Drive folder is left alone (decision 2); the response says so.
**Validate:** `pytest tests/test_web_jobs.py -q -k delete` → no rows left for that URL in any table; the same URL
for another user is untouched; a test lists every `job_url` table from the schema so a new one can't be missed.
**Status:** ✅ 2026-10-28 (5f514b5)

### Task 3: Job page UI
**Runs:** unattended
**Files:** dashboard/src/pages/JobPage.tsx, dashboard/src/api.ts, dashboard/src/types.ts (modify), a new
dashboard/src/components/EditJobDialog.tsx; tests
**What:** An "Edit" button opens a dialog with the fields (reuse `AddJobDialog`'s inputs). A "Delete job" button in a
danger zone at the bottom asks to confirm by name ("Delete {title} at {company}? Drafts, interviews and notes go too;
files in Google Drive stay.") and returns to the Jobs list.
**Validate:** `npm test -- JobPage` → edit saves and re-renders; delete confirms, calls the API, navigates home.
**Status:** ✅ 2026-10-28 (1f26d04)

## Validation
- `scripts/validate.sh --full` passes.

## Human test steps (preprod)
1. Edit a job's company and deadline → the list and page show the new values; Rescore is offered.
2. Delete a job with a draft and an interview → gone from the list; its Drive folder is still there.

## Decisions (proposed, confirm in review)
1. The URL stays fixed (it's the key in six tables). A wrong URL means delete and re-add.
2. Delete leaves Drive files; the user can trash the folder by hand. (Alternative: move it to Drive's trash.)
3. Hard delete, no undo. (Alternative: an `archived` flag hidden from the list.)

## Build notes (2026-10-28)
- Tests live in `tests/web/test_job_edit_delete.py` (there is no `tests/test_web_jobs.py`).
- `score_stale` compares a new `fields_edited_at` column with `assessed_at`, so a Rescore clears it.
- From the self-review: hand-edited work mode, deadline and location are kept by extraction and classify
  (`edited_fields`, `database.keep_edited`); an edited location also sets `location_city/state/country`; the
  assessment uses a corrected company; Open in Claude renames and moves existing draft Docs after a title/company edit;
  delete discards an open panel run that included the job and removes its local draft files (unless another user's row
  for the same posting uses them).
- Open: a discovery run can re-add a deleted discovered job (no tombstone); a task already running finishes.
