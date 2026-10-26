# Plan: Profile Docs, part 3: Claude setup, Profile and Panel pages
**Status:** 🟡 Code done 2026-10-26, preprod test pending
**Risk:** review (dashboard pages; removes the in-app library and resume editing)
**Depends on:** profile-docs-2-api

## Goal
First-time setup lives on the Claude setup page. A "Set up Profile Docs" step creates `Strelitzia/Profile/`. If it's already
filled, it warns first: "This will overwrite: <names>. Continue?". The page shows the new project instructions and offers
the rules as "Download .md" and "Copy". The Profile page no longer edits the content library or uploads a resume. Instead
it shows links to the two Profile Docs, when each was last synced, any problems, and a "Sync now" button. The Panel page
offers the rubric the same way as the rules. The old endpoints that only the removed UI used are deleted.

## Context
- API from part 2: `POST /profile/docs/setup {overwrite}` (409 with `existing`), `POST /profile/docs/sync`,
  `GET /profile` → `profile_docs`, `/claude/setup` → `rules_markdown`, `rules_version`, `project_instructions`;
  `/panel` → `rubric_markdown`; downloads at `/claude/rules.md`, `/panel/rubric.md`.
- `dashboard/src/pages/ClaudeSetupPage.tsx:16-134`: `publish()` (calls `publishClaudeDocs`, to remove), `copyInstructions()` (pattern for Copy).
- `dashboard/src/pages/ProfilePage.tsx:23-208`: `library` state, `onUpload`, the textarea and `content_library_error` (`:197`), all to remove.
- `dashboard/src/pages/PanelPage.tsx`: rubric link (`rubric.url`) becomes Download/Copy.
- `dashboard/src/api.ts:119-127,310-331` and `dashboard/src/types.ts` (`ClaudeSetup`, `ProfileResponse`, `PanelOverview`, `ResumeUploadResult`).
- `src/strelitzia/web/app.py`: `publish_claude_docs` (`POST /claude/docs`), `post_profile_resume` (`POST /profile/resume`),
  `ProfileBody.content_library_md` and the `docs` list in `claude_setup`: remove now. Keep `GET /profile/resume`.
- Gotcha: say on the setup step that the app can only see files it created. A file added to `Profile/` by hand or by Claude is
  invisible to it, so edit the two Docs and don't create new ones. Also say the old `Strelitzia/_Claude/` Docs are no longer
  used and can be deleted.

## Tasks
### Task 1: Claude setup page
**Runs:** unattended
**Files:** dashboard/src/pages/ClaudeSetupPage.tsx (modify), dashboard/src/api.ts (modify), dashboard/src/types.ts (modify), dashboard/src/__tests__/ClaudeSetupPage.test.tsx (modify), dashboard/src/__tests__/fixtures.ts (modify)
**What:** Steps in order: 1. Connect Google Drive (as today). 2. Set up Profile Docs: a button calls setup; on 409, show the
names and "Overwrite" / "Cancel"; when done, links to both Docs. 3. Create the Claude project: instructions plus Copy (as
today), then "Download rules (.md)" and "Copy rules", showing the rules version. Remove the publish button and the Docs list.
**Validate:** `cd dashboard && npm test -- ClaudeSetupPage` → passes: the overwrite confirm path, download link href, copy.
**Status:** ✅ 2026-10-26 (d192b5d)

### Task 2: Profile page
**Runs:** unattended
**Files:** dashboard/src/pages/ProfilePage.tsx (modify), dashboard/src/__tests__/ProfilePage.test.tsx (modify)
**What:** Remove the content library textarea, its error, and the resume upload. Add a "Content library and resume" section:
when `profile_docs` is set, show both links with "last synced <relative time>", a Sync now button, and any problems as a
list (role="alert"). When it isn't set, show "Set them up on the Claude setup page" with a link. The other fields and Save are unchanged.
**Validate:** `cd dashboard && npm test -- ProfilePage` → passes: links, sync success, sync problems, not-set-up state.
**Status:** ✅ 2026-10-26 (60e30fe)

### Task 3: Panel page and removing old endpoints
**Runs:** unattended
**Files:** dashboard/src/pages/PanelPage.tsx (modify), dashboard/src/__tests__/PanelPage.test.tsx (modify), src/strelitzia/web/app.py (modify), tests/web/test_profile_api.py (modify)
**What:** Panel: "Download rubric (.md)" and "Copy rubric" replace the Doc link. Server: delete `POST /claude/docs` and
`POST /profile/resume`, drop `content_library_md` from `ProfileBody`, and drop `docs` from `/claude/setup` (update or remove their tests).
**Validate:** `cd dashboard && npm test` and `pytest tests/web -q` → pass.
**Status:** ✅ 2026-10-26 (64ac8a0)

## Validation
- `scripts/validate.sh --full` passes (it runs the dashboard tests and build).

## Human test steps (preprod)
Owner account, `https://preprod.engineerfamily.net/strelitzia/dashboard/`.
1. Claude setup → Set up Profile Docs → the warning lists both Docs (part 2 created them) → Cancel → nothing changes.
2. Download rules (.md) → the file starts with `Rules version:`. Copy rules → the clipboard holds the same text.
3. Profile → no library box and no upload; both Doc links open the right Docs; Sync now → "last synced just now".
4. Break a role heading in the library Doc → Sync now → the problem is listed. Fix it → Sync now → clear.
5. Panel → Download rubric works.

## Decisions
1. The Profile page only links to the Docs, so there's one place to edit.
2. Setup asks before overwriting, because re-running setup is how the old content got lost.
