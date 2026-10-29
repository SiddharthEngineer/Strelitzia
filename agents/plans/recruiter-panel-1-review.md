# Plan: Recruiter panel 1/2: one application, graded A+ to F- by a recruiter (backend)
**Status:** ❌ Not started (planned with the user 2026-10-27)
**Risk:** low (user, 2026-10-27: merge without a review wait; protected paths still get the automated review and preprod check; was review: replaces the panel module and its tables)
**Depends on:** —

## Goal
Replace the blind A/B panel with a recruiter review of one job's application. The grader plays a recruiter hiring for
this job, uses the job description as the hiring criteria, and grades the resume and the cover letter A+ to F- on
each criterion, with evidence and a concrete fix per criterion. The prompt is self-contained, so the same review can be
run in Claude (Haiku, Sonnet, Opus), ChatGPT or Gemini, and the replies compared.

## Why (from #19 and the user, 2026-10-27)
- First-vs-second comparison didn't help: it says which draft won, not what to fix. M23 (the A/B check) was cancelled.
- The review will feed three streams: per-job feedback for the user, recurring problems that call for profile
  changes, and rules changes for the admin. Users never tune prompts themselves. Those streams are Backlog drafts
  (`recruiter-panel-3/4/5`), to be revised once this panel has produced real feedback (user, 2026-10-27). Keep the
  stored reply complete (evidence and fix per criterion, grader and model) so they have data to build on.

## Context
- `src/strelitzia/scoring/panel.py` (639 lines): A/B selection, two packets, `REPLY_SCHEMA`, `import_grades`,
  `record_pick`, `panel_report`, `panel_due`. Reuse `workbench._Doc`, `extract_json`, `schema_errors`, `posting_of`,
  `instructions_version_warning`; `scoring/targets.targets()` gives required/preferred qualifications.
- Tables `panel_runs`, `panel_items`, `panel_grades` (`database.py:267-284`); `USER_TABLES` (`:310`).
- `web/app.py:427-523` the panel endpoints. `drafts` table (`database.py:263`) holds `resume_text`, `cover_json`,
  `rules_version` for every accepted draft.
- Workbench endpoints are owner-only today (`app.py:255` `_owner_content`, "other accounts get them in #48"), so in
  practice reviews are owner-only until that opens up. Don't add a new gate; reuse the same one.

## Tasks
### Task 1: Criteria and scale (research brief)
**Runs:** unattended (the user signed off the list on 2026-10-27)
**Files:** agents/research/recruiter-panel.md (new)
**What:** Short brief on how recruiters screen (6-10 s scan, ATS match, hiring-manager read) and AI-text tells, ending
in the criteria. Starting list (decision 1), each graded separately for the resume and the cover letter:
1. **Relevance**: required/preferred qualifications from the posting shown (quote the evidence; partial counts).
2. **Evidence**: claims backed by concrete work, scope and results; nothing inferred or inflated.
3. **Human tone**: reads as written by the candidate; no AI tells (stock phrases, rule-of-three lists, buzzwords).
4. **Specificity**: written for this company and role, not a template (weighs most for the cover letter).
5. **Clarity**: a recruiter sees the fit in 10 seconds; scannable, no filler.
6. **Polish**: grammar, consistency, length (one page; cover letter under ~350 words).
Plus an **overall** grade per document and a **verdict**: phone screen yes / maybe / no, with the top three fixes.
**Validate:** the brief's Decisions record the list below as signed off by the user (2026-10-27), unchanged.
**Status:** ✅ 2026-10-29 (this commit)

### Task 2: Review module and tables
**Runs:** unattended
**Files:** src/strelitzia/scoring/review.py (new), src/strelitzia/database.py (modify), tests/test_review.py (new)
**What:**
- Scale: `GRADES = A+ A A- B+ B B- C+ C C- D+ D D- F+ F F-` (15 steps, `grade_points()` maps A+ = 14 … F- = 0 for
  averages).
- Tables: `reviews (id, user_id, job_url, draft_id, prompt_version, created_at)` and
  `review_grades (review_id, grader, model_label, overall_resume, overall_cover, verdict, detail_json, created_at,
  PRIMARY KEY (review_id, grader))`. Add `reviews` to `USER_TABLES`.
- `GRADERS = claude-haiku, claude-sonnet, claude-opus, chatgpt, gemini, other` (`model_label` is free text, e.g.
  "GPT-5 Thinking", so the comparison knows the exact model).
- `review_prompt(job, draft) -> str`: role ("You are a recruiter hiring for {title} at {company}; the job description
  below is your hiring criteria"), the criteria and scale, the posting (description + required/preferred lists), the
  resume text and cover letter text, then the reply format with an example. Self-contained: no project, connector or
  file needed. `PROMPT_VERSION` = hash of the fixed parts.
- `REPLY_SCHEMA`: `{review: 1, prompt_version, resume: Doc, cover_letter: Doc, verdict, top_fixes[3]}`, Doc =
  `{criteria: {name: {grade, evidence, fix}}, overall}`. `import_reply(conn, user_id, review_id, grader, model_label,
  text)` validates and stores (replacing that grader's earlier reply). `extract_json` must accept ChatGPT/Gemini
  output: a fenced block with or without the `json` tag, or bare JSON as the whole reply; test each.
**Validate:** `pytest tests/test_review.py -q` → prompt has every criterion and both documents; good replies import
for each grader; wrong grade strings, missing criteria and wrong prompt_version give clear errors/warnings.
**Status:** ❌

### Task 3: Review API (next to the old panel)
**Runs:** unattended
**Files:** src/strelitzia/web/app.py (modify), tests/test_web_review.py (new)
**What:** `POST /jobs/{key}/reviews` (latest draft; 409 when none), `GET /jobs/{key}/reviews`,
`GET /reviews/{id}` (prompt + replies), `POST /reviews/{id}/replies` (422 with errors, else warnings + review),
`GET /reviews` (the user's reviews, newest first, with overall grades per grader). Leave the `/panel*` endpoints and
`panel.py` in place: the old Panel page still uses them until 2/2 replaces it (decision 3).
**Validate:** `pytest tests/test_web_review.py -q` → full flow for two graders; another user's review → 404.
**Status:** ❌

## Validation
- `scripts/validate.sh --full` passes; the old Panel page still works.

## Human test steps (preprod)
Covered in 2/2 (needs the page). On preprod for this PR, only check that the Panel page still loads.

## Decisions
1. (User, 2026-10-27) Signed off as listed: the six criteria, graded per document, plus overall and verdict.
2. (Proposed) Old A/B panel data is left in its tables, unused, after 2/2; the user drops the tables by hand after a
   backup (manual step), since agents never drop data.
3. 1/2 and 2/2 are separate runner builds, so 1/2 only adds; 2/2 swaps the page and removes the A/B code
   (changed 2026-10-27 from "one PR").
4. (User, 2026-10-27) Replace A/B entirely; graders include ChatGPT and Gemini via copy-paste; no API calls.
