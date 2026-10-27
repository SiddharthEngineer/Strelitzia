# Plan: Resume quality 2/5: responsibility bullets, a Summary instead of the headline, and questions before drafting
**Status:** ❌ Not started (planned with the user 2026-10-27)
**Risk:** low (user, 2026-10-27: merge without a review wait; protected paths still get the automated review and preprod check; was review: rules, draft format, renderer and content-library format)
**Depends on:** resume-quality-1-evidence

## Goal
Every bullet is about a meaningful responsibility or accomplishment (scope, outcome, stakes), and passes the six
"earns its place" checks in `agents/research/resume-bullets.md` §3. Tools may be named in a bullet as evidence (1-3,
preferably ones the posting asks for), but a tool is never the reason a bullet exists. Small technical work is folded
into the responsibility it served. The keyword headline goes away; Claude adds a 1-2 line Summary only when a trigger
in `agents/research/resume-sections.md` §1 applies. Before drafting, Claude asks the user whatever would make the
bullets better.

## Diagnosis (2026-10-27 draft)
- The rules force tool bullets: "Cover every evidenced required qualification at least once, in a bullet that cites a
  backing project" plus "use the posting's exact term". When a posting lists Pandas, PyArrow and Spark as required,
  Claude wrote a bullet per library, each a small task described by how the code works.
- The library feeds it: many projects now carry a "Used Pandas to..." sentence, so Pandas is "evidenced" by a dozen
  projects, and the facts are file- and function-level, which reads as tasks.
- "Write fresh from the facts" discards the base resume's bullets, which are already responsibility-level. The draft
  spent 4 of 6 current-role bullets on one project and dropped three other projects.
- The headline rule and its example ("Data engineer building Airflow and Spark pipelines...") invite a keyword line.

## Context
- `src/strelitzia/scoring/workbench.py:217-246`: Honesty and Wording rules (the cover-every-qualification rule, the
  headline rule); `:262-282` `RESUME_DRAFT_EXAMPLE` and `EXAMPLE_RESULT` headline.
- `src/strelitzia/scoring/draft_docs.py:45`, `:103-146`: the `Headline:` key line in the draft format.
- `src/strelitzia/scoring/template.py:286-295`, `:339-346`; `src/strelitzia/config/resume_template.default.html`.
- `src/strelitzia/scoring/validator.py:563-578` `validate_wording`.
- `src/strelitzia/scoring/content_library.py:135-212` `_parse_project` (fields); `src/strelitzia/profile_sync.py:31-55`
  `TEMPLATE_LIBRARY`.
- The "Working with me" rules section from resume-quality-1 (Task 2) is where the question prompts go.
- Gotcha: old drafts with a `Headline:` line must still parse (as the Summary).

## Tasks
### Task 1: Bullet rules and questions
**Runs:** unattended
**Files:** src/strelitzia/scoring/workbench.py (modify), tests/test_workbench_packet.py (modify)
**What:** Replace the cover-every-qualification rule with: the six checks from `resume-bullets.md` §3 (quoted as a
checklist Claude runs on each bullet before writing); "start from the base resume's bullet for that work and adapt it
to the posting"; "fold small technical work into the responsibility it served (§5)"; "name 1-3 tools per bullet when
they are in the posting or needed for context; Skills holds the full inventory, so a posting's required tools are
covered there"; "order bullets by relevance to the posting's core responsibilities". Two worked before/after examples
from §4 replace the current example bullet.
Add to "Working with me" (interactive; the user may ask freely):
- "Before drafting, show me your plan: for each role, which projects you'll feature and why, in one line each, and ask
  if I want changes."
- "When a featured project has no outcome or number, ask me for one (what changed, for whom, how often, how big). If I
  give one, offer to add it to the project in my Content Library."
- "When you are unsure whether a Summary helps, ask me."
**Validate:** `pytest tests/test_workbench_packet.py -q` → no "Cover every evidenced required"; the checklist and the
plan-first question are in the rules.
**Status:** ❌

### Task 2: Warnings for task-level bullets
**Runs:** unattended
**Files:** src/strelitzia/scoring/validator.py (modify), src/strelitzia/scoring/workbench.py (modify), tests/test_workbench_validate.py (new)
**What:** `validate_bullet_shape(resume) -> list[str]`, warnings only: a bullet naming more than 3 tools from the base
resume's Skills; two or more bullets in one role citing only the same single project (task splitting); a bullet whose
text left after removing tool names is under 60 characters (the tool is the point). Shown with the other warnings.
**Validate:** `pytest tests/test_workbench_validate.py -q` → the research's "Before" #1 warns; its "After" #1 doesn't.
**Status:** ❌

### Task 3: Summary replaces headline
**Runs:** unattended
**Files:** src/strelitzia/scoring/draft_docs.py (modify), src/strelitzia/scoring/template.py (modify), src/strelitzia/config/resume_template.default.html (modify), tests/test_draft_docs.py (modify), tests/test_resume_template.py (modify)
**What:** Keep the model field `headline` (it now holds the Summary, so `resume_model.py` is unchanged). `Summary:` key
line (≤ 300 characters, empty = none) rendered as a short paragraph under the contact line; `Headline:` still parses
as Summary. Rules (Claude's call per job): "Leave Summary empty unless my current title doesn't match the role, there's
a domain switch or gap, or the page is short; then 1-2 lines: role noun, years, one specialization matching the
posting, one proof point; no tool list, no adjectives about me. Say why in Notes for me."
**Validate:** `pytest tests/test_draft_docs.py tests/test_resume_template.py -q` → Summary renders; an old Headline draft parses.
**Status:** ❌

### Task 4: Content-library format: Responsibility and Detail
**Runs:** unattended
**Files:** src/strelitzia/scoring/content_library.py (modify), src/strelitzia/profile_sync.py (modify), tests/test_content_library.py (modify)
**What:** Two optional project fields: `**Responsibility:**` (one line, what you owned and for whom; Claude's starting
point for the bullet) and `**Detail:**` (code-level facts for interviews and for folding in; numbers there still count
as facts; the rules say "never make a bullet out of Detail alone"). Update `TEMPLATE_LIBRARY`.
**Validate:** `pytest tests/test_content_library.py -q` → both fields parse; a library without them still parses.
**Status:** ❌

## Validation
- `scripts/validate.sh --full` passes.

## Human test steps (preprod)
1. After M36 (library revision), regenerate a recent job's drafts: Claude first shows its project plan and asks.
2. Every bullet passes the six checks by eye; tools appear only as context; the current role covers 4+ projects.
3. Summary appears only with a reason in Notes for me.

## Decisions (user, 2026-10-27)
1. Summary: Claude's call per job, with a reason in Notes for me.
2. Naming tools in bullets is fine; the problem is bullets whose purpose is a tool or a small task. No skills-only
   library list. Mechanical checks are warnings, not errors.
3. Claude may ask questions freely (resume-quality-1 adds the "Working with me" section).
