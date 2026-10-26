# Plan: Draft Docs, part 3: "Check & format" on the job page, paste removed
**Status:** 🟡 Code done 2026-10-26, preprod test pending
**Risk:** review (job page workflow; removes the paste box and the paste endpoint)
**Depends on:** docs-drafts-2-api

## Goal
The job page's "Resume & cover letter" panel works only through Drive. "Open in Claude" shows links to the packet and the
two draft Docs, plus the prompt to copy. "Check & format" reads the drafts. If they pass, it shows the new draft version and
links to the PDFs. If not, it lists the problems and offers "Copy fix prompt" to paste into Claude. The paste box, the
clipboard-only (inline) packet and the JSON paste endpoint are removed. Without Drive connected, the panel says to connect
Drive on the Claude setup page.

## Context
- `dashboard/src/components/WorkbenchPanel.tsx:22-120`: `openInClaude` (`:30`), `checkAndSave` (paste, `:49`), `copyFix` (`:67`).
- `dashboard/src/api.ts:98-118`: `openPacket`, `pasteResult` (to replace with `checkDrafts(key)` → `POST /jobs/{key}/drafts/check`;
  422 carries `errors` and `fix_prompt`, like `pasteResult` today). `dashboard/src/types.ts`: `PacketResult`, `PasteOutcome`.
- `dashboard/src/__tests__/JobPage.test.tsx`, `api.test.ts`, `fixtures.ts`: the workbench tests to update.
- `src/strelitzia/web/app.py:293-345`: `post_packet` (inline fallback and `drive_error`), `post_result`, both trimmed now.
- `src/strelitzia/scoring/workbench.py:341-413,415-450,563-575`: `job_packet(inline=True)` branch, `extract_result`, `import_result`:
  remove the paste-only code. Keep `extract_json` (the panel still uses it, `scoring/panel.py:19,379`).
- Gotcha: the API returns 409 when Drive isn't connected. Show that as the "connect Drive" message, not as an error toast.

## Tasks
### Task 1: Workbench panel
**Runs:** unattended
**Files:** dashboard/src/components/WorkbenchPanel.tsx (modify), dashboard/src/api.ts (modify), dashboard/src/types.ts (modify)
**What:** As in Goal. After Open in Claude: three links (packet, resume draft, cover letter draft) and Copy prompt.
"Check & format" is disabled until the drafts exist (`resume_draft_url` on the job). On success, call `onSaved` as today.
**Validate:** `cd dashboard && npm run build` → succeeds.
**Status:** ✅ 2026-10-26 (607d020)

### Task 2: Tests for the panel
**Runs:** unattended
**Files:** dashboard/src/__tests__/JobPage.test.tsx (modify), dashboard/src/__tests__/api.test.ts (modify), dashboard/src/__tests__/fixtures.ts (modify)
**What:** Replace the paste tests with: links shown after open; check success; check 422 lists problems and copies the fix
prompt; 409 shows the connect-Drive message; no textarea is rendered.
**Validate:** `cd dashboard && npm test` → passes.
**Status:** ✅ 2026-10-26 (f3ea117)

### Task 3: Remove the paste path on the server
**Runs:** unattended
**Files:** src/strelitzia/web/app.py (modify), src/strelitzia/scoring/workbench.py (modify), tests/web/test_workbench_api.py (modify), tests/test_workbench_import.py (modify)
**What:** Delete `POST /jobs/{key}/result`, `PastedResult` and the inline packet fallback (no Drive gives 409). Delete
`import_result`, `extract_result` and `job_packet`'s inline branch (`packet_for(..., inline=...)` callers updated). Move the
tests that exercised checks through `import_result` onto `import_data`.
**Validate:** `pytest tests -q` → passes, and `grep -rn "import_result\|/result\"" src/` → nothing.
**Status:** ✅ 2026-10-26 (65b0c88)

## Validation
- `scripts/validate.sh --full` passes.

## Human test steps (preprod)
Owner account.
1. Job page → Open in Claude → three Doc links and Copy prompt; no paste box.
2. Have Claude fill the drafts → Check & format → draft version shown; Resume and Cover letter PDF links open formatted PDFs.
3. Edit a bullet in the resume Doc to cite a slug from another role → Check & format → problem listed → Copy fix prompt → paste
   into Claude → Claude fixes the Doc → Check & format passes.
4. Disconnect Drive on Claude setup → job page says to connect Drive. Reconnect.

## Decisions
1. Removing the paste path leaves one way in, as the user chose; Drive is now required for the workbench.
2. The panel's grade paste (`extract_json`) is a separate flow and stays.
