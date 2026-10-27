# Plan: Recruiter panel follow-up: recurring problems point to profile changes (stream 3)
**Status:** 💤 Backlog draft (2026-10-27): revise against real reviews once R63-R64 are live and ~10 jobs are reviewed; not queued
**Risk:** review
**Depends on:** recruiter-panel-2-dashboard, resume-quality-4-about-me (R59: About me Doc and its interview prompts)

## Goal
After several reviews, the user sees the problems that keep coming back (say, "Evidence" at C or below on 4 of 6 jobs,
"no metrics for the data platform work"), and gets a prompt that walks them through fixing the cause in their profile:
the Content Library, the Base Resume, or the About me answers. Fixing a draft fixes one job; fixing the profile fixes
every later one.

## Context
- R59 adds the About me Profile Doc and interview prompts that fill it and revise the library
  (`agents/plans/resume-quality-4-about-me.md`): reuse that prompt mechanism rather than a new one.
- Profile Docs: `src/strelitzia/profile_sync.py` (Content Library, Base Resume in `Strelitzia/Profile/`); Sync now on
  the Profile page pulls edits back.
- Theme grouping of free-text fixes is a language task: do it in the user's chat (no API spend), not in the app.

## Tasks
### Task 1: Patterns
**Runs:** unattended
**Files:** src/strelitzia/scoring/review.py (modify), tests/test_review.py
**What:** `patterns(conn, user_id, last=10) -> Patterns`: over the user's latest review per job (newest 10 jobs), per
criterion and document: how many jobs graded C+ or lower, mean grade, and the fixes graders gave (with job). A criterion
is "recurring" at 3+ jobs and at least 40% of them (decision 1). Needs 3+ reviewed jobs, else empty.
**Validate:** `pytest -q -k patterns` → fixtures with 5 jobs flag the right criteria.
**Status:** ❌

### Task 2: Profile check-up prompt
**Runs:** unattended
**Files:** src/strelitzia/scoring/review.py, src/strelitzia/web/app.py (modify); tests
**What:** `GET /reviews/patterns` and `checkup_prompt(patterns)`: the recurring criteria with their fixes and job
names, then "Group these into causes. For each, say whether it comes from my Content Library (missing projects,
results, metrics), my Base Resume, or my About me answers, and interview me one question at a time to fill the gap.
Write accepted changes into the Profile Doc they belong in." Points at the Profile Docs by name, like R59's prompts.
No resume text in the prompt (the Docs are the source).
**Validate:** `pytest -q -k checkup` → the prompt names each recurring criterion and its jobs.
**Status:** ❌

### Task 3: On the Panel and Profile pages
**Runs:** unattended
**Files:** dashboard/src/pages/PanelPage.tsx, dashboard/src/pages/ProfilePage.tsx (modify); tests
**What:** Panel page: a "Recurring problems" section (criterion, how many jobs, sample fixes) with "Copy profile
check-up prompt". Profile page: a one-line notice when patterns exist, linking there. After Sync now, the next reviews
show whether the criterion improves (the trend per criterion over time).
**Validate:** `npm test -- PanelPage ProfilePage`.
**Status:** ❌

## Human test steps (preprod)
1. With 3+ reviewed jobs sharing a weak criterion → Recurring problems lists it.
2. Copy the check-up prompt into the Strelitzia Resumes project → Claude groups causes and asks questions; accepted
   changes land in the Content Library / About me Docs; Sync now picks them up.

## Decisions
1. (Proposed) "Recurring" = C+ or lower on 3+ of the last 10 reviewed jobs and at least 40% of them.
