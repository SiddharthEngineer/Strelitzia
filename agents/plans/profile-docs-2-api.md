# Plan: Profile Docs, part 2: the API reads Strelitzia/Profile/ before every use
**Status:** 🟡 Code done 2026-10-26, preprod test pending
**Risk:** review (changes where the workbench gets the content library; touches `web/`)
**Depends on:** profile-docs-1-sync

## Goal
Once a user has set up their Profile Docs, the content library and base resume always come from them: the app pulls both
Docs before building a packet or checking a result, and on "Sync now". If a Doc can't be read or parsed, the action stops
with the problems instead of using an old copy. Setup and sync get API endpoints. The rules and panel rubric are no longer
written to Drive. They are downloaded as `.md` files for Claude project knowledge instead, and Claude's reply names the
rules version it used, so the app can warn when the project holds an old copy. Users who haven't set up Profile Docs keep
today's behaviour (the database copy).

## Context
- `src/strelitzia/profile_sync.py` (part 1): `profile_docs`, `existing_docs`, `setup_profile_docs`, `ProfileDocsExist`,
  `pull_profile`, `SyncResult`.
- `src/strelitzia/web/app.py:249-310`: `_owner_content`, `_workbench_inputs`, `_drive_state`, `_drive_client`, `post_packet`
  (calls `publish_static_docs` on every packet). `:313-345` `post_result`. `:346-380` `claude_setup`, `publish_claude_docs`.
  `:383-400` `get_panel` (rubric Doc URL). `:859-975` profile endpoints (`_profile_out`, `get_profile`, `ProfileBody`, `put_profile`).
- `src/strelitzia/scoring/workbench.py:67-97`: `result_schema`. `:198-256` `_rules()` (Output format section). `:518-556`
  `check_result` (where warnings are built). `:712-775` `PROJECT_INSTRUCTIONS`, `STATIC_DOCS`, `RESUME_DOCS`,
  `publish_static_docs`.
- `src/strelitzia/scoring/panel.py`: `rubric_text()`, `PROJECT_INSTRUCTIONS`.
- `src/strelitzia/cli.py:338-353`: `_doctor_library_row`.
- Gotcha: `RULES_VERSION` is a hash of `rules_doc()`, so the version can't sit inside the hashed text. Put it in the
  downloaded file's first line (`Rules version: <v>`). The rules body tells Claude to copy that line's value into `rules_version`.
- Gotcha: the dashboard isn't changed until part 3, so keep `POST /profile/resume`, `POST /claude/docs` and the
  `content_library_md` field working here (part 3 removes them). Once Profile Docs are set up, `PUT /profile` with a
  `content_library_md` that differs from the stored one returns 409 "Edit your content library in the Google Doc".

## Tasks
### Task 1: Pull before use
**Runs:** unattended
**Files:** src/strelitzia/web/app.py (modify), tests/web/test_workbench_api.py (modify)
**What:** `_workbench_inputs(request)` first calls `_fresh_profile(request)`. When the user has Profile Docs (`profile_docs`
has ids), it gets `_drive_client`, which is required (409 "Connect Google Drive on the Claude setup page" when None). It
then runs `pull_profile`, and any problems give 409 `{"detail": "Your Profile Docs have problems", "problems": [...]}`.
Without Profile Docs, nothing changes. `post_packet` stops calling `publish_static_docs`.
**Validate:** `pytest tests/web/test_workbench_api.py -q` → new tests: a Doc edit shows up in the next packet; a parse problem gives 409 with problems and no packet; no Profile Docs uses the database copy.
**Status:** ✅ 2026-10-26 (b8d7f6a)

### Task 2: Setup and sync endpoints
**Runs:** unattended
**Files:** src/strelitzia/web/app.py (modify), tests/web/test_profile_api.py (modify)
**What:** `POST /profile/docs/setup {overwrite: bool}` returns the profile, or 409 `{"detail", "existing": [names]}` from
`ProfileDocsExist`. `POST /profile/docs/sync` returns `{"ok", "problems", "changed"}` plus the profile. `GET /profile` adds
`profile_docs: {library|resume: {url, synced_at} | null}`. `PUT /profile` refuses a changed `content_library_md` as in Context.
Owner only (`_owner_content`), like the workbench.
**Validate:** `pytest tests/web/test_profile_api.py -q` → passes: setup, the overwrite 409 and retry, sync, the PUT refusal.
**Status:** ✅ 2026-10-26 (f9b99ff)

### Task 3: Rules and rubric as downloads, with a version check
**Runs:** unattended
**Files:** src/strelitzia/scoring/workbench.py (modify), src/strelitzia/web/app.py (modify), tests/test_workbench_import.py (modify), tests/web/test_panel_api.py (modify)
**What:** `rules_markdown() -> str` (`Rules version: <v>` line, then `rules_text()`) and the same for the rubric in
`panel.py` (`rubric_markdown()`). `GET /claude/rules.md` and `GET /panel/rubric.md` return them as attachments
(`text/markdown`, names `Strelitzia rules <v>.md` and `Strelitzia panel rubric.md`). `/claude/setup` adds
`rules_markdown`. `/panel` adds `rubric_markdown`. `STATIC_DOCS` and `publish_static_docs` drop the `library` Doc.
Schema: an optional `rules_version` string. The rules' Output format section says to copy the version line.
`check_result` warns "Claude used rules version X; download the current rules (Y) into the project" when it's missing or
different. `PROJECT_INSTRUCTIONS` becomes: the rules come from project knowledge, and at the start of each chat Claude opens
"Content Library" and "Base Resume" in Google Drive folder Strelitzia/Profile with the Google Docs
connector and uses only their facts. It may edit those two Docs only when I ask.
**Validate:** `pytest tests/test_workbench_import.py tests/web/test_panel_api.py -q` → passes, with a test for the version warning (matching, missing, old).
**Status:** ✅ 2026-10-26 (3eb6d43)

### Task 4: Doctor reports the Profile Docs
**Runs:** unattended
**Files:** src/strelitzia/cli.py (modify), tests/test_doctor_content_library.py (modify)
**What:** When the owner has Profile Docs, `_doctor_library_row` adds "from Google Drive Strelitzia/Profile, last synced <time>".
Otherwise it keeps today's text.
**Validate:** `pytest tests/test_doctor_content_library.py -q` → passes.
**Status:** ✅ 2026-10-26 (230b23d)

## Validation
- `scripts/validate.sh --full` passes.
- `curl -s localhost:<port>/api/claude/rules.md | head -1` against `strelitzia serve` → `Rules version: <8 hex>`.

## Human test steps (preprod)
Use the owner account. The dashboard pages change in part 3, so this uses the API from the browser console or curl.
1. `POST /strelitzia/dashboard/api/profile/docs/setup` with `{"overwrite": false}` → Drive now has `Strelitzia/Profile/`
   with "Content Library" and "Base Resume", filled with your current content.
2. Run it again → 409 listing both Docs.
3. In the content library Doc, add a skill to a project (e.g. pandas) → open a job's Claude packet on the job page → the
   packet's evidence reflects it, and `GET /api/profile` shows the new text.
4. Delete the `## ` from one role heading in the Doc → open a packet → error listing the problem. Put it back.
5. `GET /api/claude/rules.md` downloads the rules with a version line.

## Decisions
1. Pulls happen on use, not on a timer: always fresh, and no background Drive traffic.
2. Users without Profile Docs keep the database copy, so nothing breaks before setup.
3. Old endpoints stay until part 3, so each merge leaves a working dashboard.
4. The rules version is a warning, not an error: an old rules copy shouldn't block a good draft.
