# Plan: Recruiter panel follow-up: review feedback improves the rules (admin stream)
**Status:** 💤 Backlog draft (2026-10-27): revise against real reviews once R63-R64 are live and ~10 jobs are reviewed; not queued
**Risk:** review
**Depends on:** recruiter-panel-2-dashboard; worth running only after ~10 reviewed jobs

## Goal
The admin (the owner) uses reviews across jobs to improve the resume and cover-letter rules, and can see whether a
rules change helped. End users never touch prompts: their side is streams 2 and 3.

## Context
- The rules are code: `scoring/workbench.py:212-314` `_rules()`, `rules_text()`, `RULES_VERSION` (a hash); R60 adds
  the cover-letter rules. Each draft stores its `rules_version` (`drafts` table), so every review knows which rules
  produced the draft it graded.
- A rules change is a PR (via `/plan`), so this stream's output is a proposal the admin turns into a plan, not an
  automatic edit.
- #19 asks to "look into prompt optimizer tools". Automated optimizers (DSPy MIPROv2/GEPA, TextGrad) need many scored
  LLM runs through an API, which the copy-paste flow doesn't have; spend needs the user's OK (memory: confirm cost first).

## Tasks
### Task 1: Prompt-optimizer research brief
**Runs:** interactive (findings reviewed with the user)
**Files:** agents/research/prompt-optimizers.md (new)
**What:** DSPy (MIPROv2, GEPA), TextGrad, promptfoo (eval harness), Anthropic Console's prompt improver and eval tool.
For each: what it needs (a metric, a dataset, API calls), what it would cost per run with the review as the metric,
and whether it fits a copy-paste flow. End with a recommendation: likely "use the chat-based review below now; revisit
an API-driven loop once 30+ reviewed jobs exist", with the estimated cost of that loop.
**Validate:** the user reads the brief and records a decision in it.
**Status:** ❌

### Task 2: Rules report (owner only)
**Runs:** unattended
**Files:** src/strelitzia/scoring/review.py, src/strelitzia/web/app.py (modify); tests/test_web_review.py
**What:** `GET /admin/rules-report`, owner only (403 otherwise): per rules version (resume and cover letter), how many
reviewed drafts, mean grade per criterion, verdict mix, and the most common fixes. Scope = all users' reviews or only
the owner's (decision 1); either way only grades and fix text, never resume or letter text.
**Validate:** `pytest -q -k rules_report` → two rules versions compared; a non-owner gets 403.
**Status:** ❌

### Task 3: Rules review prompt
**Runs:** unattended
**Files:** src/strelitzia/scoring/review.py (modify), dashboard/src/pages/PanelPage.tsx (modify, owner-only section); tests
**What:** "Copy rules review prompt": the current resume (and cover-letter) rules text, the rules report, then "Propose
specific edits to these rules that would fix the recurring problems. For each: the rule text before and after, which
problems it addresses, and the risk (what it could make worse). Don't propose edits for problems that come from
missing profile content." The admin takes the answer into `/plan`. The section also shows the report table, so after a
rules change ships the next reviews show whether grades moved.
**Validate:** `pytest -q -k rules_prompt` and `npm test -- PanelPage` → the section shows for the owner only.
**Status:** ❌

## Human test steps (preprod)
1. As owner, with 5+ reviews: Panel → Rules section shows grades by rules version; the prompt copies.
2. As the dev test account (non-owner): no Rules section; `/admin/rules-report` → 403.

## Decisions
1. (Open) Report scope: every user's reviews (better signal, but the owner sees other users' feedback text) or only the
   owner's. Proposed: all users, grades and fixes only, since only the owner tunes rules.
2. (User, 2026-10-27) Prompt optimization is the admin's job; end users only get per-job and profile feedback.
