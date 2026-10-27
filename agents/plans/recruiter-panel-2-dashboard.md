# Plan: Recruiter panel 2/2: review on the job page, scorecards and grader comparison
**Status:** ❌ Not started (planned with the user 2026-10-27)
**Risk:** review
**Depends on:** recruiter-panel-1-review (same PR, see its decision 3)

## Goal
From a job with a draft, the user starts a recruiter review, copies the prompt into any chat app, pastes the reply
back and sees a scorecard. The Panel page lists all reviews and compares graders (which model grades how, and how
much they agree), which answers #19's "try out different LLMs".

## Context
- `dashboard/src/pages/PanelPage.tsx` (373 lines) and `__tests__/PanelPage.test.tsx`: the A/B page, replaced.
- `dashboard/src/App.tsx:89-91,107,113`: Panel nav link with a "due" badge (`panelDue`, `refreshPanelDue`): remove the
  badge (no more "due" logic).
- `dashboard/src/pages/JobPage.tsx`, `components/WorkbenchPanel.tsx` (Check & format lives here).
- Copy/paste patterns to reuse: `components/PastePanel.tsx`, the copy buttons on `ClaudeSetupPage.tsx`.

## Tasks
### Task 1: Review box on the job page
**Runs:** unattended
**Files:** dashboard/src/components/ReviewPanel.tsx (new), dashboard/src/pages/JobPage.tsx, dashboard/src/api.ts,
dashboard/src/types.ts (modify); tests
**What:** Under the workbench, once a draft exists: "Get a recruiter review" → creates a review. Then: grader picker
(Claude Haiku/Sonnet/Opus, ChatGPT, Gemini, Other + model name), Copy prompt, links to claude.ai / chatgpt.com /
gemini.google.com, a paste box, Import. Errors show inline like Check & format's. A review made for an older draft
says so ("this review is of draft v3; v4 is newer").
**Validate:** `npm test -- ReviewPanel` → create, copy, import (ok and error) for two graders.
**Status:** ❌

### Task 2: Scorecard
**Runs:** unattended
**Files:** dashboard/src/components/Scorecard.tsx (new); test
**What:** A table per document: criteria as rows, one column per grader (grade chip, coloured by band A/B/C/D/F),
evidence and fix on expand. Header: overall grades, verdict, top three fixes. With 2+ graders, a criterion where they
differ by more than one letter band is marked "graders disagree".
**Validate:** `npm test -- Scorecard` → renders 1 and 3 graders; disagreement mark appears for A- vs C+.
**Status:** ❌

### Task 3: Panel page = reviews list + grader comparison
**Runs:** unattended
**Files:** dashboard/src/pages/PanelPage.tsx (rewrite), dashboard/src/App.tsx (modify), src/strelitzia/scoring/review.py,
src/strelitzia/web/app.py (modify: `GET /reviews/graders`); tests
**What:** The page lists reviews (job, date, draft version, overall per grader, verdict) linking to the job. A "Graders"
section, from reviews with 2+ graders: per grader the mean grade per criterion, how often its verdict matched the
others, and its spread (is it harsh, lenient, or all B's). Keep the page name "Panel" (decision 1).
**Validate:** `pytest tests/test_web_review.py -q -k graders` and `npm test -- PanelPage`.
**Status:** ❌

## Validation
- `scripts/validate.sh --full` passes.

## Human test steps (preprod)
1. On a job with a draft: Get a recruiter review → copy the prompt into a Claude Sonnet chat → paste the reply → a
   scorecard with six criteria per document.
2. Run the same prompt in ChatGPT and Gemini, paste each → three columns; any disagreements are marked.
3. Panel page: the review is listed; Graders shows the three models.

## Decisions
1. (Proposed) Keep the nav name "Panel"; the "Strelitzia Panel" Claude project becomes optional (the prompt is
   self-contained). Its instructions are cut to one line pointing at the prompt; M-step to update it.
