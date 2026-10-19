# Plan: switch Strelitzia to the shared agent-runner and delete `scripts/agent/`
**Status:** ❌ Not started
**Risk:** low (no prod impact; auto-merges on green CI, user 2026-10-19)
**Depends on:** strelitzia-runner-config, plus the cutover (agent-runner ROADMAP AM5) and a week without trouble on the new runner

## Goal
The cutover moved cron to the installed agent-runner. This plan moves Strelitzia's PIV commands to the `agent-runner` CLI and deletes
the old runner copy (`scripts/agent/`, its tests, and `validate.sh --preprod`). After it, only one runner exists, and Strelitzia's agent docs
point at it (design: agent-runner `shared-agent-runner.md`, Rollout step 7).

## Context
- Task 0 check: `crontab -l | grep -q 'agent-runner/current/run.sh\|bin/agent-runner run'` and `! crontab -l | grep -q scripts/agent/run.sh`
  (cutover done), and `command -v agent-runner`. If any check fails, write the result file `blocked` naming it and stop.
- Commands to switch: `.claude/commands/implement.md:37,42` (gate, inbox ask), `schedule-build.md:6,12-14,22,26` (queue, preprod status,
  state path, crontab check), `ship.md:6,12,15` (run.sh, gate, preprod deploy), `plan.md:21,23` (gate). Map: `python3 scripts/agent/X.py` →
  `agent-runner {queue|gate|inbox}`, `scripts/agent/preprod.sh` → `agent-runner preprod`, `gate.py <plan>` → `agent-runner gate <plan> --config agents/runner.toml`.
  `/schedule-build` adds `--repo strelitzia`.
- `.claude/settings.json:10-13` allows the old script paths. The unattended implementer can't edit this file (denied in `agents/settings/implement.json`), so Task 3 is interactive.
- References to remove: `scripts/validate.sh:6,36-40` (the `--preprod` mode), `AGENTS.md:17`, `agents/DEPLOY.md:16,19,50-52`, `tests/test_agent_runner.py` (the whole file).

## Tasks
### Task 1: commands use the CLI
**Runs:** unattended
**Files:** .claude/commands/implement.md (modify), .claude/commands/schedule-build.md (modify), .claude/commands/ship.md (modify), .claude/commands/plan.md (modify)
**What:** Apply the map from Context. The queue's state path in `schedule-build.md` becomes `~/.local/state/agent-runner/`.
The crontab check looks for `agent-runner`.
**Validate:** `grep -rn 'scripts/agent' .claude/commands` → no matches. `agent-runner check-commands strelitzia agent-runner` → `same` for every command, or only expected differences (dashboard and `--full`).
**Status:** ❌

### Task 2: delete the old runner
**Runs:** unattended
**Files:** scripts/agent/ (delete), tests/test_agent_runner.py (delete), scripts/validate.sh (modify), AGENTS.md (modify), agents/DEPLOY.md (modify)
**What:** `git rm -r scripts/agent tests/test_agent_runner.py`. Remove `--preprod` from `validate.sh` (its usage line, the arg case
and the block). AGENTS.md: replace the `scripts/agent/` mention with "the shared runner (SiddharthEngineer/agent-runner) builds this
repo from `agents/runner.toml`". DEPLOY.md: worktrees are under `~/.local/state/agent-runner/worktrees/strelitzia/`, preprod is
`agent-runner preprod`, and the netrc is in `~/.config/agent-runner/`.
**Validate:** `scripts/validate.sh --full` → all PASS; `grep -rn 'scripts/agent\|strelitzia-agent' --exclude-dir=.git --exclude-dir=done .` →
only `agents/plans/done/` history and this plan.
**Status:** ❌

### Task 3: interactive permissions
**Runs:** interactive (`.claude/settings.json` is denied to the unattended implementer)
**Files:** .claude/settings.json (modify)
**What:** Replace the four `scripts/agent` allow lines with `Bash(agent-runner queue:*)`, `Bash(agent-runner gate:*)`,
`Bash(agent-runner inbox:*)`, `Bash(agent-runner preprod status)`.
**Validate:** `grep -c scripts/agent .claude/settings.json` → `0`.
**Status:** ❌

## Validation
- `scripts/validate.sh --full` passes; CI is green.

## Human test steps (preprod)
None (low risk). In a new interactive session, `/schedule-build list` shows the agent-runner queue.

## Decisions
1. The command switch waits for the cutover, so the old runner never runs commands that call a CLI it doesn't use.
2. `.claude/settings.json` is the one interactive task: the implementer's own settings deny it on purpose.
