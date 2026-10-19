# Plan: README names the shared runner (smoke test, Strelitzia)
**Status:** ✅ Done 2026-10-19
**Risk:** low (docs only; auto-merges on green CI, user 2026-10-19)
**Depends on:** the cutover (agent-runner ROADMAP AM5, cron swapped 2026-10-19)

## Goal
README's "Running Strelitzia next to Claude Code" note cites `scripts/agent/run.sh` as the unattended runner. Since the 2026-10-19
cutover the runner is the shared `agent-runner`. Fix the example. This is also the agent-runner design's Rollout step 6 `low` smoke
test for this repo: implementer PR → merged, no validator run.

## Tasks
### Task 1: README example
**Runs:** unattended
**Files:** README.md (modify)
**What:** In the "Running Strelitzia next to Claude Code" paragraph, replace "(such as `scripts/agent/run.sh`)" with
"(such as the shared `agent-runner` that builds this repo's plans)". Change nothing else.
**Validate:** `scripts/validate.sh` → ALL PASS. `grep -n "scripts/agent/run.sh" README.md` → no match.
**Status:** ✅ 2026-10-19 (this commit)

## Validation
- `scripts/validate.sh` passes.

## Human test steps (preprod)
None (low risk).
