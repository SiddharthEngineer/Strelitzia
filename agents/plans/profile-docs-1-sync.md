# Plan: Profile Docs, part 1: Drive read and the Profile sync module
**Status:** ❌ Not started
**Risk:** low (new module and Drive helpers; nothing calls them yet)
**Depends on:** none

## Goal
Lay the groundwork for `Strelitzia/Profile/` in Google Drive becoming the source of truth for the content library and the
base resume. This part adds the code to create the two Profile Docs and to pull them back into the database and local
files. Nothing in the web app or CLI calls it yet; part 2 wires it in, and part 3 adds the dashboard.

Why: the content library was edited in two places (the Profile tab, i.e. the database, and the "Strelitzia content library"
Doc), and the app only ever wrote database → Doc, so edits made in the Doc were overwritten and never reached the checks.

## Context
- `src/strelitzia/storage/drive.py:31-56`: scope is `drive.file`, so the app can only see files it created. `DOC_MIME`,
  `_FILE_FIELDS`. `:288-300` media helpers; `:300-345` `DriveClient` (injectable service); `:428-462` `upsert_doc` and
  `download`, the patterns to mirror.
- `src/strelitzia/storage/drive_layout.py:78-85`: `CLAUDE_FOLDER` / `claude_folder_path()`: mirror for `Profile`.
- `src/strelitzia/scoring/content_library.py:135-240`: `_parse_project`, `parse_content_library_text` (needs
  `## CURRENT ROLE` / `## PRIOR ROLE` headings, `### ` projects, `- **Context:**` style fields).
- `src/strelitzia/profile.py:37-60,129-165`: `UserProfile`, `load_profile`, `save_profile(..., with_resume=False)`;
  `resume_text` and `content_library_md` are the database copies. `:246-275` `import_owner_files` reads the owner's local
  files on first start only.
- `src/strelitzia/config.py:68-72`: `RESUME_PATH`, `CONTENT_LIBRARY_PATH` (the owner's local copies, used by the CLI).
- `src/strelitzia/scoring/workbench.py:721-775`: per-user state via `get_state`/`set_state` with a `{user}:…` key: mirror it.
- `tests/fake_drive.py:42-130`: the fake Drive service; extend it with `export` and `modifiedTime`.
- Gotcha: Claude's Google Docs connector and Google's own editor turn markdown into real headings, bold and lists, so read
  the library with Drive's `text/markdown` export and tolerate its quirks: `*` or `-` bullets, `\` escapes (`\-`, `\*`,
  `\_`, `\#`), `__bold__`, blank lines between list items, heading levels shifted by one. Read the base resume as `text/plain`.
- Gotcha: create the Docs by uploading markdown (content library) or plain text (resume) with the `DOC_MIME` target type,
  so Google converts them into formatted Docs.

## Tasks
### Task 1: Drive export and the Profile folder
**Runs:** unattended
**Files:** src/strelitzia/storage/drive.py (modify), src/strelitzia/storage/drive_layout.py (modify), tests/fake_drive.py (modify), tests/test_drive_client.py (modify)
**What:** `drive_layout`: `PROFILE_FOLDER = "Profile"`, `profile_folder_path() -> list[str]`, `PROFILE_DOCS = {"library":
"Strelitzia content library", "resume": "Strelitzia base resume"}`. `DriveClient`: `export_text(file_id, mime) -> str`
(`files().export`), `doc_meta(file_id) -> dict | None` (id, name, modifiedTime, trashed, webViewLink; None if gone), and
`create_doc_from_text(folder_id, name, text, source_mime, known_id=None) -> DriveFile` (same in-place update logic as
`upsert_doc`, with `text/markdown` or `text/plain` media). Add `modifiedTime` to `_FILE_FIELDS`. The fake stores the uploaded
text and returns it from `export`.
**Validate:** `pytest tests/test_drive_client.py -q` → passes, with new tests for export, doc_meta on a trashed file, and in-place update.
**Status:** ✅ 2026-10-26 (this commit)

### Task 2: Parse a Docs markdown export
**Runs:** unattended
**Files:** src/strelitzia/scoring/content_library.py (modify), tests/test_content_library.py (modify), tests/fixtures/content_library_docs_export.md (new)
**What:** `normalize_docs_markdown(text: str) -> str`: undo the export quirks listed in Context (unescape, `*` → `-`
bullets, `__x__` → `**x**`, drop blank lines inside lists, map `#`/`###` role headings back to `##` when they start with
CURRENT/PRIOR ROLE). `parse_content_library_text` calls it first. The fixture is `tests/fixtures/content_library_sample.md`
rewritten with those quirks.
**Validate:** `pytest tests/test_content_library.py -q` → the fixture parses to the same roles, projects, fields and angles as `content_library_sample.md`.
**Status:** ❌

### Task 3: Profile sync module
**Runs:** unattended
**Files:** src/strelitzia/profile_sync.py (new), tests/test_profile_sync.py (new)
**What:**
```python
@dataclass
class ProfileDocs:  # stored per user in state "{user}:profile_doc:{kind}" as {"id","url","synced_at","modified"}
    library: dict | None; resume: dict | None
def profile_docs(conn, user_id) -> ProfileDocs
def existing_docs(client, conn, user_id) -> list[str]   # names of Profile Docs the app can still see (stored ids, else same-named Docs in Profile/)
def setup_profile_docs(client, conn, user_id, *, overwrite: bool) -> ProfileDocs
    # raises ProfileDocsExist(names) when existing_docs() is non-empty and not overwrite.
    # Seeds from the database copy; when it is empty, from TEMPLATE_LIBRARY / TEMPLATE_RESUME (example text, no personal data).
@dataclass
class SyncResult: ok: bool; problems: list[str]; changed: bool
def pull_profile(client, conn, user_id, *, is_owner: bool) -> SyncResult
    # export both Docs; parse the library (an empty parse or a ValueError is a problem; projects missing Angles are problems);
    # on ok: save content_library_md + resume_text with profile.save_profile, and for the owner write CONTENT_LIBRARY_PATH and
    # RESUME_PATH; store synced_at/modified. On any problem nothing is saved. A missing/trashed Doc is a problem naming it.
class ProfileDocsExist(Exception): names: list[str]
```
**Validate:** `pytest tests/test_profile_sync.py -q` → passes: seed from database, seed from templates, refuse without overwrite, overwrite updates in place, pull saves database + local files (owner only, in tmp APP_DIR), parse error saves nothing, trashed Doc reported.
**Status:** ❌

## Validation
- `scripts/validate.sh --full` passes.

## Human test steps (preprod)
None (low risk; nothing calls this yet). Part 2 tests it end to end.

## Decisions
1. The Profile Docs are the source of truth; the database and the owner's local files are copies refreshed by `pull_profile`.
2. A pull with any problem saves nothing, so a broken Doc never replaces good data.
3. Setup never overwrites without an explicit `overwrite=True`, because `drive.file` makes the app blind to files it didn't create.
