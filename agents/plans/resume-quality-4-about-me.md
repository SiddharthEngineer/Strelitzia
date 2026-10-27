# Plan: Resume quality 4/5: an About me Profile Doc and per-job "why this company" notes
**Status:** ❌ Not started (planned with the user 2026-10-27)
**Risk:** review (Profile Docs sync, a job column, API and dashboard)
**Depends on:** resume-quality-2-bullets (Task 4's library interview uses its Responsibility/Detail fields)

## Goal
Claude gets the personal material a good cover letter needs and a resume never holds: how the candidate got into the
field, proudest work and the hard decision in it, an incident they handled, goals, why each target industry, values,
constraints (work authorisation, relocation) and a writing sample for voice. It lives in a third Profile Doc,
"About me", in `Strelitzia/Profile/`, answered once. Each job also gets a short "Why this company" note on the job page,
written by the user before opening the cover letter chat.

## Diagnosis
- Nothing in the inputs says anything personal: the library and base resume are work facts only, so the letter could
  only be built from project facts. The research (`agents/research/cover-letter.md`) says the letter must supply what the
  resume can't: motivation, judgement, goals, a specific reason for this company.
- Work authorisation was reported "unevidenced" because no input could ever state it.

## Context
- `src/strelitzia/storage/drive_layout.py:81` `PROFILE_DOCS` (add `"about": "About me"`).
- `src/strelitzia/profile_sync.py:27-28` `_MIME`; `:31-76` templates (add `TEMPLATE_ABOUT` with the 13 questions from
  `agents/research/cover-letter.md` §5, each a `## heading` with an empty answer); `:133-156` setup; `:171-` pull
  (store the text; no parsing beyond "has at least one answer").
- `src/strelitzia/database.py` jobs additive columns (pattern from docs-drafts-2): add `cover_notes` (TEXT).
- `src/strelitzia/web/app.py:140-200` job detail; add `PUT /jobs/{key}/cover-notes`.
- `dashboard/src/pages/JobPage.tsx` (a textarea "Why this company, referrals, anything to stress" near Open in Claude);
  `dashboard/src/pages/ProfilePage.tsx` (link to the About me Doc next to the other two).
- Gotcha: `drive.file` scope: the app must create the About me Doc itself (Setup / Sync creates a missing one without
  touching the other two).
- Gotcha: About me is personal data: never in the repo, logs or test fixtures (use a made-up fixture).

## Tasks
### Task 1: About me Doc
**Runs:** unattended
**Files:** src/strelitzia/storage/drive_layout.py (modify), src/strelitzia/profile_sync.py (modify), tests/test_profile_sync.py (modify)
**What:** Third Profile Doc kind; setup creates it when missing (no overwrite of the others); pull stores its text per
user; a pull with every answer empty is a warning, not an error.
**Validate:** `pytest tests/test_profile_sync.py -q` → setup on a user with two Docs creates only About me.
**Status:** ❌

### Task 2: Cover notes per job
**Runs:** unattended
**Files:** src/strelitzia/database.py (modify), src/strelitzia/web/app.py (modify), tests/web/test_job_detail.py (modify)
**What:** `cover_notes` column, returned in the job detail, saved by `PUT /jobs/{key}/cover-notes` (owner of the row
only, ≤ 2000 characters).
**Validate:** `pytest tests/web/test_job_detail.py -q` → round trip; another user's job → 404.
**Status:** ❌

### Task 3: Dashboard
**Runs:** unattended
**Files:** dashboard/src/pages/JobPage.tsx (modify), dashboard/src/pages/ProfilePage.tsx (modify), dashboard/src/__tests__/JobPage.test.tsx (modify)
**What:** The notes box (saves on blur) with the per-application questions 14-17 as placeholder text; the About me link
on the Profile page.
**Validate:** `scripts/validate.sh --full` → dashboard tests pass.
**Status:** ❌

### Task 4: Interview prompts
**Runs:** unattended
**Files:** src/strelitzia/scoring/workbench.py (modify), dashboard/src/pages/ProfilePage.tsx (modify), dashboard/src/__tests__/ProfilePage.test.tsx (modify), tests/test_workbench_packet.py (modify)
**What:** Two copyable prompts on the Profile page, for a new chat in the Strelitzia Resumes project:
- `ABOUT_ME_INTERVIEW`: "Interview me to fill my About me Doc: one question at a time, in the Doc's order, skipping
  ones already answered; ask follow-ups until the answer has a specific moment or example; write each answer into the
  Doc in my words, and show me before you write."
- `LIBRARY_INTERVIEW` (manual step M36): "Go through my Content Library one project at a time: propose a one-line
  Responsibility, move code-level facts into Detail, and ask me for the outcome, who relied on it and any number when
  they're missing. Write each project back only after I agree."
Both are served with the project instructions (`GET /claude-setup`, existing) so the version check covers them.
**Validate:** `pytest tests/test_workbench_packet.py -q` and `scripts/validate.sh --full` → both prompts render with Copy buttons.
**Status:** ❌

## Validation
- `scripts/validate.sh --full` passes.

## Human test steps (preprod)
1. Profile → Sync now → an About me Doc appears in `Strelitzia/Profile/` with the questions.
2. On a job, type notes, reload → they stay.

## Decisions (user, 2026-10-27)
1. About me is a Google Doc in `Strelitzia/Profile/`: easy to write long answers in, and Claude reads and updates it.
2. Claude fills it by interviewing the user (Task 4) as well as from the user's own writing.
