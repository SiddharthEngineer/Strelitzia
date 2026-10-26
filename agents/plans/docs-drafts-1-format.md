# Plan: Draft Docs, part 1: the readable draft format and its parser
**Status:** ✅ Done 2026-10-26
**Risk:** low (new parser and a refactor of the import path; no UI or endpoint changes)
**Depends on:** profile-docs-3-dashboard (uses `normalize_docs_markdown` from profile-docs-1-sync)

## Goal
Today Claude ends each chat reply with a JSON block that the user pastes into the job page. The draft-Docs feature has
Claude write the resume and cover letter into two Google Docs in the job's Drive folder, in a readable format the user can
also edit by hand. A "Check & format" button then checks them and makes the PDFs. This part defines that format: render it
(to seed a Doc) and parse it back into the same result dict the JSON paste produces, so every existing check and the
renderer are reused unchanged.

## Context
- `src/strelitzia/scoring/workbench.py:67-97`: `result_schema` (the dict shape to produce: `resume.headline`, `resume.roles[].role_key`,
  `.bullets[].text`, `.bullets[].project_ids`, `resume.skills[].category/items`, `resume.dropped_roles`, `cover_letter.paragraphs`,
  `cover_letter.evidence_slugs` or null, `notes_for_user`, `rules_version` from profile-docs-2).
- `:415-450`: `extract_json`, `extract_result` (paste path). `:518-556`: `check_result`. `:563-628`: `import_result`, to split.
- `src/strelitzia/scoring/content_library.py`: `normalize_docs_markdown` (part 1 of profile-docs). Draft Docs are read with
  the same `text/markdown` export, so the same quirks apply.
- `tests/test_workbench_import.py`, `tests/workbench_helpers.py`: fixtures for a library, a job and a valid result.

### The format
Resume Doc:
```
Rules version: 1a2b3c4d
Headline: Data engineer who ships reliable pipelines

## <role-key>
- Bullet text written for the posting [project-slug, other-slug]

## Dropped roles
- <role-key>

## Skills
- Languages: Python, SQL
- Data: pandas, pyarrow

## Notes for me
Free text (unevidenced qualifications and anything else for the user).
```
Cover letter Doc: an optional `Rules version:` line, then the paragraphs separated by blank lines, then a last line
`Evidence: slug-a, slug-b`. An empty cover letter Doc (only whitespace or the seed's placeholder) means `cover_letter: null`.

## Tasks
### Task 1: Render and parse the resume draft
**Runs:** unattended
**Files:** src/strelitzia/scoring/draft_docs.py (new), tests/test_draft_docs.py (new)
**What:**
```python
class DraftFormatError(ValueError):  # .errors: list[str], each naming the line or section, e.g. 'Line 7: bullet has no [slug] tags'
def resume_draft_text(result: dict | None, library: ContentLibrary, rules_version: str) -> str
    # result=None → a skeleton: Headline line, one `## <role-key>` per library role with a placeholder bullet, empty Skills
def parse_resume_draft(text: str) -> tuple[dict, str | None, str]   # (resume dict, rules_version, notes_for_user)
```
Known sections are role keys, `Dropped roles`, `Skills` and `Notes for me`. An unknown `##` heading is kept as a role key,
and the existing schema check rejects it with the valid keys listed. A missing `Headline:` is an empty headline. Placeholder
bullets left from the skeleton are an error.
**Validate:** `pytest tests/test_draft_docs.py -q` → render → parse round-trips the helpers' valid result; Docs-export quirks (`*` bullets, `\[`, `\-`) parse the same; each error case names its line.
**Status:** ✅ 2026-10-26 (9b20930)

### Task 2: Render and parse the cover letter draft
**Runs:** unattended
**Files:** src/strelitzia/scoring/draft_docs.py (modify), tests/test_draft_docs.py (modify)
**What:** `cover_draft_text(cover: dict | None, rules_version: str) -> str` (None → a placeholder line) and
`parse_cover_draft(text) -> dict | None`. A missing `Evidence:` line is an error. Also add
`drafts_to_result(resume_text, cover_text) -> dict` (the full result dict, with `strelitzia: SCHEMA_VERSION`, `rules_version`
from the resume Doc, else the cover Doc).
**Validate:** `pytest tests/test_draft_docs.py -q` → passes, including an empty letter → `cover_letter is None`.
**Status:** ✅ 2026-10-26 (9b20930)

### Task 3: Split the import path
**Runs:** unattended
**Files:** src/strelitzia/scoring/workbench.py (modify), tests/test_workbench_import.py (modify)
**What:** Move everything in `import_result` after `extract_result` into `import_data(conn, job, data: dict, inputs=None,
out_dir=None, cover_dir=None) -> ImportOutcome`. `import_result` becomes extract + `import_data`. Add
`import_drafts(conn, job, resume_text, cover_text, inputs=None, ...) -> ImportOutcome`: `drafts_to_result`, and a
`DraftFormatError` becomes `ImportOutcome(ok=False, errors=e.errors, fix_prompt=...)`. Add `fix_prompt(errors, where="docs")`,
which says "fix them in the two draft Docs and change nothing else" instead of asking for JSON.
**Validate:** `pytest tests/test_workbench_import.py -q` → all existing tests pass unchanged, plus `import_drafts` accepts a rendered valid draft and rejects a broken one with no draft saved.
**Status:** ✅ 2026-10-26 (6b47dc9)

## Validation
- `scripts/validate.sh --full` passes.

## Human test steps (preprod)
None (low risk; nothing calls this yet).

## Decisions
1. Drafts parse into the existing result dict, so the checks and PDF rendering stay the single source of rules.
2. `[slug]` tags at the end of each bullet keep provenance checkable while the Doc stays readable.
3. Unknown sections are passed to the schema check rather than dropped, so a typo in a role key is reported, not silently lost.
