# Plan: Resume quality 5/5: the cover letter gets its own chat, rules and checks
**Status:** ❌ Not started (planned with the user 2026-10-27)
**Risk:** low (user, 2026-10-27: merge without a review wait; protected paths still get the automated review and preprod check; was review: packet flow, rules, validator, API and dashboard)
**Depends on:** resume-quality-4-about-me, resume-quality-2-bullets

## Goal
The cover letter is written in its own Claude chat, after the resume is accepted, from a cover-letter packet: the
posting, the accepted resume, the About me Doc, the job's cover notes and the cover-letter rules from
`agents/research/cover-letter.md`. The letter tells 1-2 stories with motivation and a specific reason for this company,
in 4 paragraphs and 250-350 words, instead of restating the resume.

## Diagnosis (2026-10-27 letter)
- The rules prescribed a technical letter: "Paragraph 1: a specific thing I built... Paragraph 2: two achievements from
  the resume's cited projects, with numbers. Paragraph 3: one thing about the company from the posting." Claude followed
  them: three paragraphs of tools and project facts.
- 250 words and exactly 3 paragraphs leave no room for a story and a motivation.
- The same chat writes the resume first, so the letter is drafted from the bullets just written.
- No personal input exists (plan 4 adds it). "No narration about yourself" in the rules forbids the very thing a letter
  is for.

## Context
- `src/strelitzia/scoring/workbench.py:248-256` the Cover letter rules; `:436-466` `job_packet` and its prompt;
  `:774-850` `packet_for`, `publish_packet`, `publish_drafts`; `:568-610` `check_result` (resume and letter checked
  together); `COVER_MAX_WORDS`.
- `src/strelitzia/scoring/validator.py:421-476` `validate_cover_letter`; `:581-612` `validate_letter` (exactly 3
  paragraphs, numbers backed by evidence slugs).
- `src/strelitzia/web/app.py:336-405` packet and drafts/check endpoints; `dashboard/src/pages/JobPage.tsx`.
- Gotcha: `PROJECT_INSTRUCTIONS` change bumps `INSTRUCTIONS_VERSION` → a manual step to repaste them (like M35).

## Tasks
### Task 1: Cover-letter packet and prompt
**Runs:** unattended
**Files:** src/strelitzia/scoring/workbench.py (modify), tests/test_workbench_packet.py (modify)
**What:** `cover_packet(job, inputs) -> Packet` (own Doc, "… – Cover letter packet"): posting, the accepted resume text,
the cover notes, a pointer to About me, and `_cover_rules()` (research §1-4 and §6, with `[NEEDS INPUT: ...]` for missing
facts). The resume packet and rules drop the cover-letter section and say "resume only". `PROJECT_INSTRUCTIONS` names
both kinds of chat.
The cover rules' "Working with me" section (interactive, Claude may ask freely):
- "Before drafting, read About me and my cover notes, then ask me about anything the letter needs that they don't
  answer: why this company, a referral, why this industry if About me doesn't cover it."
- "Propose 2-3 candidate stories, one line each with the posting responsibility it maps to, and ask which to use."
- "For the chosen story, ask me one or two questions about the stakes, the decision I made and what I took from it,
  if the library and About me don't already say."
- "Write `[NEEDS INPUT: ...]` only for a question I chose to skip. After the letter, offer to save new reusable answers
  to About me."
**Validate:** `pytest tests/test_workbench_packet.py -q` → the resume packet has no cover rules; the cover packet has
the notes, the About me pointer and the story-choice question.
**Status:** ✅ 2026-10-27 (this commit)

### Task 2: Letter checks
**Runs:** unattended
**Files:** src/strelitzia/scoring/validator.py (modify), src/strelitzia/scoring/cover_letter.py (modify), src/strelitzia/config/cover_letter_template.default.html (modify), tests/test_workbench_validate.py (modify), tests/test_cover_letter_pdf.py (modify)
**What:** `validate_letter`: 3-5 paragraphs, 220-380 words, research §4 banned phrases (errors), any `[NEEDS INPUT`
marker (error naming the question), numbers still backed by cited projects or the posting; warnings for a sentence
naming more than 2 tools and for a first sentence without the company name. The greeting becomes "Dear Hiring Team,"
(`cover_letter.py:18` `GREETING`, the template, and `validator.py:468`, `:597`).
**Validate:** `pytest tests/test_workbench_validate.py tests/test_cover_letter_pdf.py -q` → a 3-paragraph tools-list letter warns; "I am writing to express" errors.
**Status:** ❌

### Task 3: Separate checks and endpoints
**Runs:** unattended
**Files:** src/strelitzia/scoring/workbench.py (modify), src/strelitzia/web/app.py (modify), tests/web/test_workbench_api.py (modify)
**What:** `POST /jobs/{key}/cover-packet` (409 until a resume draft is accepted); `drafts/check?kind=resume|cover`
checks and renders only that draft, so the resume can be accepted without a letter.
**Validate:** `pytest tests/web/test_workbench_api.py -q` → resume check passes with an empty letter Doc; cover packet
before a resume → 409.
**Status:** ❌

### Task 4: Dashboard
**Runs:** unattended
**Files:** dashboard/src/pages/JobPage.tsx (modify), dashboard/src/__tests__/JobPage.test.tsx (modify)
**What:** Two steps on the job page: "Resume: Open in Claude / Check & format", then "Cover letter: Open in Claude /
Check & format" (enabled after the resume is accepted, with the cover notes box from plan 4 above it).
**Validate:** `scripts/validate.sh --full` → dashboard tests pass.
**Status:** ❌

## Validation
- `scripts/validate.sh --full` passes.

## Human test steps (preprod)
1. Accept a resume, fill the cover notes, open the cover letter in Claude in a new chat → a 4-paragraph letter with a
   story, a motivation and a specific company reason; no tool lists.
2. Leave the notes empty → Claude asks why this company before drafting; say "skip" and it writes `[NEEDS INPUT: ...]`,
   which Check & format names.
3. Run the rubric (research §7) on the letter by hand.

## Decisions (user, 2026-10-27)
1. The letter is written in its own new chat, from its own packet, after the resume is accepted.
2. Salutation: "Dear Hiring Team,".
3. Claude asks freely before drafting (questions, story choice); `[NEEDS INPUT]` only for skipped questions.
