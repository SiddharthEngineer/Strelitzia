# Plan: Recruiter panel follow-up: per-job feedback the user acts on (stream 2)
**Status:** 💤 Backlog draft (2026-10-27): revise against real reviews once R63-R64 are live and ~10 jobs are reviewed; not queued
**Risk:** review
**Depends on:** recruiter-panel-2-dashboard, resume-quality-5-cover-letter (R60 moves the cover letter to its own chat)

## Goal
A review turns into a revision in one step: the user gets the feedback where the drafting chat can read it, and a
short prompt that asks Claude to revise the drafts from it, interactively, then runs Check & format as usual.

## Options (from the user, 2026-10-27)
- **A. Copy-paste prompt:** the feedback is inlined in a prompt for the "Strelitzia Resumes" project. Fewer steps.
- **B. Drive:** the feedback goes into the job's Drive folder; a short prompt points Claude at it. Supports an
  interactive review in the Docs.
- **Recommendation: B.** The job's folder already has the packet Doc and the "Resume draft" / "Cover letter draft" Docs
  that Claude reads and writes through the Google Docs connector (`workbench.py:772-830`), so B adds one Doc and a
  prompt the same length as A's would be. A remains the fallback when Drive isn't connected (decision 1).

## Context
- `workbench.py:404` the packet prompt is already a pointer to Docs in the job's folder; `:819` creates/reuses the draft
  Docs; `storage/drive_layout.py:93-97` `DRAFT_LABELS`, `draft_name()`.
- R57 makes the resume chat show its plan and ask first; R60 gives the cover letter its own chat. The revise prompts
  must follow whatever those plans settle (one prompt per chat).

## Tasks
### Task 1: "Recruiter review" Doc
**Runs:** unattended
**Files:** src/strelitzia/scoring/review.py, src/strelitzia/storage/drive_layout.py (modify); tests/test_review.py
**What:** `review_doc(review) -> _Doc`: the verdict, top fixes, then per document each criterion with every grader's
grade, evidence and fix (graders merged; disagreements noted). Written as "<Company> - <Role> - Recruiter review" in the
job's folder when a reply is imported (rewritten on each import). No Drive → skipped silently.
**Validate:** `pytest tests/test_review.py -q -k doc` with the fake Drive client → one Doc, rewritten not duplicated.
**Status:** ❌

### Task 2: Revise prompts
**Runs:** unattended
**Files:** src/strelitzia/scoring/review.py, src/strelitzia/scoring/workbench.py (modify); tests
**What:** `revise_prompts(job, review) -> {resume, cover_letter}`. With Drive: "Read the Recruiter review Doc for
{job} in its folder, then revise the Resume draft Doc. Show me your plan for each fix first and ask before writing;
skip a fix if it would need a fact that isn't in my library, and tell me what to add instead." Without Drive: the same,
with the review inlined. Both carry the current rules version so Check & format's version warning still works.
**Validate:** `pytest -q -k revise_prompt` → Drive and no-Drive variants; the names match `draft_name()`.
**Status:** ❌

### Task 3: Buttons on the scorecard
**Runs:** unattended
**Files:** dashboard/src/components/ReviewPanel.tsx (modify); test
**What:** Under the scorecard: "Open the review Doc" (when in Drive), "Copy resume revise prompt", "Copy cover letter
revise prompt", and a reminder that Check & format makes the new draft. After a new draft, the box offers "Review the
new draft" (a new review, so grades can be compared over versions).
**Validate:** `npm test -- ReviewPanel`.
**Status:** ❌

## Human test steps (preprod)
1. Import a review → the Recruiter review Doc appears in the job's Drive folder.
2. Copy the resume revise prompt into the Strelitzia Resumes project → Claude reads the Doc, proposes fixes, asks, then
   edits the Resume draft Doc. Check & format → new draft. Review it again → grades move.

## Decisions
1. (Proposed) Option B with A as the no-Drive fallback. Confirm.
