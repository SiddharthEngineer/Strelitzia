# Plan: Resume quality 3/5: a fixed line budget so the resume fills 95-100% of the page
**Status:** ❌ Not started (planned with the user 2026-10-27)
**Risk:** low (user, 2026-10-27: merge without a review wait; protected paths still get the automated review and preprod check; was review: packet, rules and renderer)
**Depends on:** resume-quality-2-bullets

## Goal
Every resume fills one page to 95-100%. The packet gives Claude an exact budget (bullets per role and a character band
per bullet) computed from the page; Check & format measures the fill, closes small gaps by spacing, and sends a fix
prompt for big ones.

## Diagnosis (2026-10-27 draft)
- The rendered resume ended ~2.3 inches above the bottom margin (~78% of the usable height).
- `_role_slots` caps each role at its base-resume bullet count (max = base, min = base - 2), so a draft can't grow; the
  draft also dropped a role and its company line.
- Bullets were mostly one line, where the base resume's are about two.
- `fit_to_one_page` only removes bullets on overflow; nothing reacts to underfill. `render_pdf` already returns
  `content_height_pt` and `usable_height_pt`.

## Context
- `src/strelitzia/scoring/tailor.py:13-35` `_role_slots`; `:38-69` `fit_to_one_page`.
- `src/strelitzia/scoring/pdf.py:353-403` `render_pdf` (height measurement); the template's fonts are 9.5-10pt with
  0.35in/0.5in margins, roughly 120 characters per bullet line.
- `src/strelitzia/scoring/workbench.py:403-414` (roles and bullet ranges in the packet); `:692-730` `render_outputs`.
- Gotcha: the line budget depends on the fixed blocks (education, skills lines, summary). Compute it by rendering, not
  by constants: render the base resume's fixed parts with N placeholder lines and measure.

## Tasks
### Task 1: Budget from the page
**Runs:** unattended
**Files:** src/strelitzia/scoring/tailor.py (modify), src/strelitzia/scoring/pdf.py (modify), tests/test_tailor_budget.py (new)
**What:** `line_budget(profile, fixed, roles, skills, summary) -> Budget(lines_free, chars_per_line)` renders the fixed
parts and measures. `bullet_plan(library, base, budget) -> dict[role_key, int]`: two-line bullets (band
`chars_per_line*1.6`-`chars_per_line*1.95`), most recent role 5-6, then 3-4, 2-3, 1-2 (research §3), sized so the total
lines fill 97% ± 2%.
**Validate:** `pytest tests/test_tailor_budget.py -q` → the base fixtures give a plan whose render is 95-100% full.
**Status:** ❌

### Task 2: Exact counts in the packet
**Runs:** unattended
**Files:** src/strelitzia/scoring/workbench.py (modify), tests/test_workbench_packet.py (modify)
**What:** The packet's role list says "exactly N bullets, each X-Y characters" instead of a range; the rules say the
counts and bands are binding and that a role may be dropped only if the packet says so. `validate_wording` checks the
band (error below the minimum, as today above the maximum). Add to "Working with me": "If you can't reach a role's
count with bullets that pass the checks, ask me for more material (another project, an outcome) instead of padding,
and never split one project into task bullets to hit a count."
**Validate:** `pytest tests/test_workbench_packet.py -q` → counts and bands appear; a 60-character bullet errors.
**Status:** ❌

### Task 3: Measure and close the gap
**Runs:** unattended
**Files:** src/strelitzia/scoring/workbench.py (modify), src/strelitzia/scoring/template.py (modify), tests/test_workbench_import.py (modify)
**What:** After rendering, fill = content/usable. 90-95%: raise a `--gap` CSS variable (section and bullet spacing,
bounded) and re-render until ≥95%. Below 90%: error with a fix prompt naming how many lines to add and where. Store
`fill_pct` in the draft report and show it with the warnings.
**Validate:** `pytest tests/test_workbench_import.py -q` → a 92% draft renders at ≥95% after spacing; an 80% draft errors.
**Status:** ❌

## Validation
- `scripts/validate.sh --full` passes.

## Human test steps (preprod)
1. Regenerate a recent job's drafts → the resume PDF fills the page (bottom line within ~0.3in of the margin).
2. Check & format reports the fill percentage.

## Decisions (user, 2026-10-27)
1. Two-line bullets are the unit: they match the base resume and make the fill predictable.
