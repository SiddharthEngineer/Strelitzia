# Plan: Draft Docs, part 2: draft Docs per job and "Check & format"
**Status:** ❌ Not started
**Risk:** review (new job columns, packet flow and endpoint; touches `web/` and `database.py`)
**Depends on:** docs-drafts-1-format

## Goal
When the user opens a job in Claude, the app creates (or reuses) three Docs in the job's Drive folder: the Claude packet
(as today), "… - Resume draft" and "… - Cover letter draft". The draft Docs are seeded with the current draft, or a
skeleton when there's none. Claude writes the resume and cover letter into those two Docs with the Google Docs connector.
The new endpoint `POST /jobs/{key}/drafts/check` does the rest: it pulls the Profile Docs, reads both drafts, runs every
check, renders the PDFs and DOCX, and uploads them to the job folder. On problems, it returns them with a prompt to paste
into Claude. The rules and packet prompt describe the Doc format instead of JSON.

## Context
- `src/strelitzia/scoring/draft_docs.py` (part 1): `resume_draft_text`, `cover_draft_text`. `workbench.import_drafts`, `fix_prompt(..., where="docs")`.
- `src/strelitzia/scoring/workbench.py:198-256`: `_rules()`, whose "Output format" section and JSON schema/example are replaced by the Doc
  format (copy the format block from `agents/plans/docs-drafts-1-format.md`). `:341-413`: `job_packet` (the prompt at `:395-411`).
  `:781-792`: `publish_packet` (packet Doc + `packet_doc_id`/`packet_doc_url`): mirror it for the drafts.
- `src/strelitzia/database.py:530-560`: the `jobs` additive columns dict (`packet_doc_id` at `:550`). Add `resume_draft_doc_id`,
  `resume_draft_doc_url`, `cover_draft_doc_id`, `cover_draft_doc_url`, `drafts_written_at` (all TEXT).
- `src/strelitzia/storage/drive.py`: `create_doc_from_text`, `export_text`, `doc_meta` (profile-docs-1).
- `src/strelitzia/storage/drive_layout.py:89-92`: `file_name`, `packet_folder_path`: add `draft_name(job, kind)` ("<Company> - <Role> - Resume draft").
- `src/strelitzia/web/app.py:293-345`: `post_packet`, `post_result` (pattern for the new endpoint, incl. `sync_job` upload). `:150-195`: job detail fields.
- Gotcha: reopening a packet must never wipe Claude's or the user's edits. Reseed a draft Doc only when it doesn't exist yet,
  or when its `modifiedTime` is not newer than `drafts_written_at` and a newer accepted draft exists.
- Gotcha: `drive.file` means the app can only read Docs it created. The prompt tells Claude to edit these two Docs in place,
  never create new ones.

## Tasks
### Task 1: Create the draft Docs with the packet
**Runs:** unattended
**Files:** src/strelitzia/database.py (modify), src/strelitzia/storage/drive_layout.py (modify), src/strelitzia/scoring/workbench.py (modify), tests/test_workbench_packet.py (modify), tests/test_drive_layout.py (modify)
**What:** Add the columns. `publish_drafts(client, conn, job, inputs) -> dict[str, str]` (kind → url) creates or reseeds per
the gotcha, and stores ids, urls and `drafts_written_at`. The packet (non-inline) prompt becomes: "Tailor my resume and cover
letter for the job in '<packet>'. Write the resume into the Google Doc '<resume draft>' and the cover letter into '<cover
draft>' (both in the job's folder) with the Google Docs connector. Replace each Doc's whole text, in the format in the rules,
and edit only those two Docs." `_rules()` Output format: the Doc format, with JSON removed.
**Validate:** `pytest tests/test_workbench_packet.py tests/test_drive_layout.py -q` → passes: first open creates seeded Docs; reopen after an outside edit leaves them alone; prompt names both Docs.
**Status:** ❌

### Task 2: The check endpoint
**Runs:** unattended
**Files:** src/strelitzia/web/app.py (modify), tests/web/test_workbench_api.py (modify)
**What:** `post_packet` also calls `publish_drafts` and returns `resume_draft_url` and `cover_draft_url`.
`POST /jobs/{key}/drafts/check`: owner only. Drive is required (409 otherwise). It runs `_workbench_inputs` (which pulls the
Profile Docs), exports both drafts as `text/markdown`, and calls `import_drafts`. On failure it returns 422
`{detail, errors, warnings, fix_prompt}`. On success it runs `sync_job` and returns `{outcome, job}`, the same shape as
`post_result`. The job detail adds both draft URLs.
**Validate:** `pytest tests/web/test_workbench_api.py -q` → passes with the fake Drive: valid drafts → 200 and PDFs uploaded; a bullet without tags → 422 naming the line; a missing draft Doc → 409 "Open the job in Claude first".
**Status:** ❌

### Task 3: Rules version and old paste path
**Runs:** unattended
**Files:** src/strelitzia/scoring/workbench.py (modify), tests/test_workbench_import.py (modify)
**What:** The rules tell Claude to put the `Rules version:` line at the top of the resume Doc. The warning from profile-docs-2
now reads it from there. The JSON paste path (`import_result`, `POST /jobs/{key}/result`) keeps working until part 3 removes it.
**Validate:** `pytest tests/test_workbench_import.py -q` → passes, including the version warning from a draft Doc.
**Status:** ❌

## Validation
- `scripts/validate.sh --full` passes.

## Human test steps (preprod)
Owner account; part 3 adds the button, so use the API for the check.
1. Open a job → Open in Claude → the job's Drive folder has the packet plus "Resume draft" and "Cover letter draft" Docs.
2. In the Strelitzia Resumes Claude project (with the new rules .md in knowledge), paste the prompt → Claude fills both Docs.
3. `POST /strelitzia/dashboard/api/jobs/<key>/drafts/check` → 200; the job folder gets the resume PDF and cover letter PDF.
4. Delete a `[slug]` from one bullet in the resume Doc → check again → 422 naming that line. Restore it.
5. Open in Claude again → the drafts are not overwritten.

## Decisions
1. The app creates the draft Docs, because `drive.file` can't see Docs Claude creates.
2. The packet never overwrites a draft that changed after the app last wrote it.
3. Formatting stays in the app (the PDF renderer), so the layout and one-page fit are the same as today.
