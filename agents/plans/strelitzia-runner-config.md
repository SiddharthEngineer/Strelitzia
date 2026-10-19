# Plan: Strelitzia's runner config for the shared agent-runner
**Status:** ❌ Not started
**Risk:** low (no prod impact; new files that nothing reads until the cutover; auto-merges on green CI, user 2026-10-19)
**Depends on:** agent-runner runner-7-preprod-check (the `runner.toml` schema and validator settings are final then)

## Goal
Strelitzia describes itself to the shared runner (design: agent-runner `agents/plans/shared-agent-runner.md`, D4): `agents/runner.toml`
with today's base, merge method, validate commands, risk patterns and preprod commands, plus per-role agent settings and the Playwright
MCP config under `agents/`. This only **adds** files. The old runner (`scripts/agent/`), the PIV commands and `.claude/settings.json`
don't change, so the live cron keeps working until the cutover. The command switch is strelitzia-runner-cleanup.

## Context
- Task 0 check: `git -C ~/src/agent-runner fetch -q && git -C ~/src/agent-runner show origin/main:prompts/preprod-check.md >/dev/null`
  (runner-7 merged). If it fails, write the result file `blocked` ("agent-runner runner-7-preprod-check not merged") and stop.
- Values to carry over: `scripts/agent/gate.py:25-46` (`HIGH_RISK`, `CODE_LINE_BUDGET`, `DOC_OR_TEST`), `scripts/agent/run.sh:28`
  (repo), `:209` (`--rebase`), `scripts/validate.sh` (fast/`--full`), `scripts/agent/preprod.sh:31-45` (fetch the PR head into the app
  dir, deploy, seed, health). The preprod commands are in the user's runner env (not in this repo): app dir `/srv/Strelitzia-preprod`, deploy
  `make -C /srv/engineerfamily-preprod preprod-strelitzia-up`, the seed `docker compose … run … python /seed/scripts/seed_preprod.py`. Ask
  for nothing: the exact seed command is in agent-runner's `tests/fixtures/strelitzia.runner.toml` (runner-1-config), so copy it from there.
- Schema and templates: agent-runner `config.py`, `tests/fixtures/strelitzia.runner.toml`, `agents/settings/*.json` (runner-8-self-host).
  Read them with `git -C ~/src/agent-runner show origin/main:<path>`.
- `scripts/agent/settings.json` and `mcp.json`: today's implementer permissions and MCP. The new files start as copies.
- Health URL: go through Cloudflare, not `127.0.0.1` (design D5): `https://preprod.engineerfamily.net/strelitzia/dashboard/api/health`, `json_ok`.

## Tasks
### Task 1: `agents/runner.toml`
**Runs:** unattended
**Files:** agents/runner.toml (new)
**What:** `[repo] name="strelitzia", github="SiddharthEngineer/Strelitzia", base="trunk", merge="rebase"`; validate `scripts/validate.sh`
and `scripts/validate.sh --full`; `[gate]` from `gate.py` with `scripts/agent/*` replaced by `agents/runner.toml`, `agents/settings/*`,
`agents/mcp.json`; `[preprod] app_dir="/srv/Strelitzia-preprod"`, the deploy/seed commands from the fixture, health per Context.
**Validate:** `python3 ~/src/agent-runner/config.py check agents/runner.toml` → `ok` (agent-runner on `origin/main`).
**Status:** ✅ 2026-10-19

### Task 2: agent settings and MCP
**Runs:** unattended
**Files:** agents/settings/implement.json (new), agents/settings/validate.json (new), agents/mcp.json (new)
**What:** `implement.json` = `scripts/agent/settings.json`, with `python3 scripts/agent/{inbox.py ask,gate.py}` replaced by
`agent-runner inbox ask:*` and `agent-runner gate:*`, `Read(//home/dev/.config/agent-runner/**)` denied alongside the old dir, and
`Edit(agents/settings/**)` and `Edit(agents/runner.toml)` denied. `validate.json` = agent-runner's `settings/validate.json` plus this
repo's validate commands (`.venv/bin/*`, `npm … dashboard`). `mcp.json` = `scripts/agent/mcp.json`.
**Validate:** `.venv/bin/python -c` one-liner: all three parse; `implement.json` denies `Bash(gh pr merge:*)` and `Bash(make:*)`;
`validate.json` denies `Edit` and `Bash(git push:*)`.
**Status:** ✅ 2026-10-19

### Task 3: docs
**Runs:** unattended
**Files:** AGENTS.md (modify), agents/DEPLOY.md (modify)
**What:** AGENTS.md map: `agents/runner.toml`, `agents/settings/`, `agents/mcp.json` ("read by the shared agent-runner after the cutover;
`scripts/agent/` is the live runner until then"). DEPLOY.md preprod section: one line saying the preprod commands now also live in `agents/runner.toml`.
**Validate:** `scripts/validate.sh` → all PASS.
**Status:** ✅ 2026-10-19

## Validation
- `scripts/validate.sh --full` passes.
- `git diff --stat origin/trunk` lists only new files under `agents/` plus the two docs: nothing the old runner reads changed.

## Human test steps (preprod)
None (low risk; nothing deploys and nothing reads these files yet).

## Decisions
1. Add-only before the cutover, so the live runner can build this plan itself and keeps working afterwards.
2. The health check moves from `127.0.0.1:8080` to the public preprod URL, which also proves the Cloudflare and nginx routing.
