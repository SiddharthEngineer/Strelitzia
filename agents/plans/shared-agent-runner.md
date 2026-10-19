# Plan: One agent runner for Strelitzia and engineerfamily, with manager, implementation and validation roles
**Status:** 📝 Design (2026-10-18; user answers folded in 2026-10-19). One open question left (D2: submodule or installed copy), then each Part becomes its own plan through `/plan`
**Risk:** review (moves the runner to a new repo, changes the agent settings and the preprod lock; touches `scripts/agent/*`, `.claude/settings.json` and `.github/*` in both repos)

This is a design plan: it is over `gate.py --plan`'s size budget on purpose and **must not be queued**. Each Part below is
sized to become one queueable plan (≤4 tasks, ≤12 files).

## Goal
engineerfamily gets the same continuous development as Strelitzia: plan with `/plan`, queue with `/schedule-build`, and a
5-minute cron picks the plan up, implements it unattended, validates it, and merges it. Deploying to prod is the only manual step.
One runner serves both repos. The work is split across three agent roles:
1. **Manager (orchestration):** decides what runs next, starts the other agents, owns the queue, the locks, the risk gate and the merge.
2. **Implementation:** implements one queued plan in a worktree and opens a PR. It can't merge or deploy.
3. **Validation:** reviews the PR with fresh context, then tests it on preprod. It can't edit code, merge or deploy prod.

Both repos use the same folder layout. The runner code lives in its own repo, `agent-runner` (D2).

## Context (read before building any Part)
- **Runner today** (`scripts/agent/`, about 1,100 lines plus 361 lines in `tests/test_agent_runner.py`):
  - `run.sh` is already the orchestrator, written in plain bash with no Claude. It holds a `flock`, polls the inbox, ticks the
    preprod lock, takes `buildqueue.py next`, checks `usage.py check`, makes worktree `agent/<slug>` from `origin/trunk`, and runs
    `claude -p "/implement agents/plans/<slug>.md --unattended"` with `scripts/agent/settings.json` and `mcp.json`. It then runs
    `validate.sh --full` again, calls `gate.py`, waits for `gh pr checks --watch`, and rebase-merges or labels the PR `awaiting-preprod`.
  - Hard-coded to Strelitzia: `GH_REPO`, `origin/trunk`, `agents/plans/`, `scripts/validate.sh`, `--rebase`, the `HIGH_RISK`
    and `DOC_OR_TEST` lists in `gate.py`, `PROJECT_LABEL`/`MARKER` in `inbox.py`, and `CONFIG_DIR`/`STATE` (`strelitzia-agent`)
    in `buildqueue.py`, `preprod.sh` and `scripts/validate.sh --preprod`.
  - Queue keys are bare slugs (`queue.json` `items[slug]`). `preprod.lock` is `pr<TAB>sha<TAB>time` and has no repo field.
  - Config lives in `~/.config/strelitzia-agent/{env,preprod.netrc}` and state in `~/.local/state/strelitzia-agent/`.
  - **Cron:** at plan time the `dev` crontab line is **commented out** (`# */5 * * * * …/Strelitzia/scripts/agent/run.sh`). The
    last run was `prefs-cleanup-3-page → done` on 2026-10-16, and every queue item is `done`. The rollout below works whether or not the line is on.
  - Cron runs `run.sh` straight from the dev clone `~/src/Strelitzia`, so the branch that clone is on decides which runner code runs.
- **Preprod is one environment shared by both repos.** The `engineerfamily-preprod` compose project contains the `strelitzia`
  service, built from `/srv/Strelitzia-preprod`. `make preprod-deploy` runs `up -d --build --remove-orphans` and so rebuilds
  Strelitzia too. Two PRs, one from each repo, therefore can't be on preprod at the same time: **the preprod lock has to be global.**
- **engineerfamily** (`~/src/engineerfamily`, default branch `main`, merge commits, public):
  - The repo has only `CLAUDE.md`, with no `agents/`, `.claude/` or PR CI. `.github/workflows/deploy.yml` is a dispatch-only deploy.
    `gh pr checks` with no checks never goes green, so the runner would never merge anything there.
  - Preprod: `make preprod-deploy ref=<sha|tag|origin/branch>` fetches all branches into `/srv/engineerfamily-preprod`, then
    recreates nginx (`--force-recreate --no-deps nginx`, because a reload keeps the old single-file bind mount).
  - Prod: `make tag-prod` and `make deploy-prod` (GitHub workflow over SSH), plus `make strelitzia-deploy`. These are the user's
    alone, every time.
  - Validation per `CLAUDE.md`: `docker compose --env-file … -f docker-compose.base.yml -f docker-compose.<env>.yml config -q`
    and `nginx -t` in `nginx:alpine` with the conf mounted. The confs use `set $upstream_x http://app:8000; proxy_pass $upstream_x;`,
    so `nginx -t` doesn't need to resolve `app`/`strelitzia`/`umami`. Check whether `ssl_certificate` paths or the
    `.htpasswd` include need stub files in CI.
  - Preprod hosts sit behind nginx basic auth (`preprod.engineerfamily.net`). The runner's `preprod.netrc` covers only `127.0.0.1` today.
- **VPS memory:** 4 GB total, and each open desktop session holds about 185 MB. An Opus run plus `validate.sh --full` (docker build)
  plus Playwright is the heaviest thing the box does. **At most one Claude run at a time**, whatever its role or repo.
- One Claude subscription feeds every role, so the 5-hour session-usage gate (`usage.py`) and the usage-limit pause are global too.

## Decisions (proposed; confirm or change in review)

### D1. One shared runner, not one per repo
Shared: the cron line, `flock`, queue, preprod lock, usage gate and pause, inbox repo and ntfy topic, and the runner code.
Per repo: plan directory, base branch, merge method, validate commands, risk-gate patterns, preprod deploy/release/health commands,
and agent settings. A runner per repo would need a cross-runner preprod lock, a cross-runner usage gate and a cross-runner
"one Claude run at a time" lock. By then it is one runner with two cron lines.

- **Queue:** one `queue.json`, keyed `<repo>/<slug>` (for example `engineerfamily/ci-validate`), with a `repo` field on each item.
  On first load, a bare `<slug>` key is read as `strelitzia/<slug>`, so the current file migrates in place.
  `buildqueue.py add <slug> --repo <name>` (`/schedule-build` passes the repo from the current checkout), and `--after` takes
  `repo/slug` across repos (an engineerfamily nginx change can wait for a Strelitzia PR).
- **Locks:** `run.lock` (one Claude run at a time) and `preprod.lock` are global. `preprod.lock` gains a repo column:
  `repo<TAB>pr<TAB>sha<TAB>time`, and a 3-column line is read as `strelitzia`.
- **Risk gate:** `gate.py` keeps its logic and diff checks. `HIGH_RISK`, `DOC_OR_TEST`, `CODE_LINE_BUDGET`, test-dir weakening
  patterns and the base branch come from the repo's config. Size budgets (`PLAN_*`) stay global: they come from Claude's context costs, not the repo.
- **One merge rule for both repos** (user, 2026-10-19; see D3): `low` merges after green CI, `review` merges after the validator
  approves. `AGENT_MERGE_POLICY` (`gate`/`all`) goes away, so there is no per-repo policy to set.
- **Cron:** one line, `*/5 * * * * ~/.local/share/agent-runner/current/run.sh` (see D2 for that path).
- **Naming:** config in `~/.config/agent-runner/` (`env` for shared secrets such as the token, inbox and ntfy;
  `repos/<name>.env` for machine-local per-repo values such as the clone path and netrc). State in `~/.local/state/agent-runner/`
  (`queue.json`, locks, `logs/`, `results/`, `worktrees/<repo>/<slug>`). For one release the runner falls back to
  `~/.config/strelitzia-agent/env`, the same way it fell back to `applypilot-agent` after the rename.

### D2. Runner code lives in its own repo, `agent-runner` (user, 2026-10-19)
A new private repo `SiddharthEngineer/agent-runner` holds `run.sh`, `buildqueue.py`, `gate.py`, `inbox.py`, `preprod.sh`,
`usage.py`, the new `config.py`, the `/review-pr` command template, and their tests, with its own CI. Each of Strelitzia and
engineerfamily keeps its own `.claude/` and `agents/` (D4); only the runner code is shared.

**How the repos get it (the one open question).** The user suggested a git submodule in both repos. Recommended instead: **one
installed copy on the VPS that both repos call.**
- **Installed copy (recommended):** `~/.local/share/agent-runner/current` is a detached checkout of an `agent-runner` tag that the user
  moves with `agent-runner/install.sh <tag>`, and `~/.local/bin/agent-runner` is a small CLI (`agent-runner queue add …`,
  `agent-runner gate --plan …`, `agent-runner inbox ask …`). Cron runs that one copy for both repos, so the repos can't be on two
  runner versions at once. The commands in each repo's `.claude/commands` call `agent-runner …` instead of `python3 scripts/agent/…`.
  Runner changes go live only when the user installs a new tag, and a session on a branch in a dev clone can't change what cron runs.
- **Submodule (the user's suggestion):** works, and pins a runner version per repo, but those versions can drift apart while
  only one copy actually runs from cron. It also adds steps: every runner worktree needs `git submodule update --init`, both CIs need
  `submodules: true`, every runner change needs a bump PR in two repos, and a private runner repo breaks public clones of Strelitzia
  (AGPL, public), so the runner repo would have to be public too.

### D3. Three roles: a deterministic manager plus two Claude agents
| Role | What runs | Can | Can't |
|---|---|---|---|
| **Manager** | `run.sh` + `buildqueue.py`/`gate.py`/`preprod.sh` (bash/Python, **no Claude** on a normal tick) | pick the next job, start an implementer or validator, hold the locks, merge under the gate, deploy and release **preprod**, notify | deploy prod, edit code |
| **Implementation** | `claude -p /implement <plan> --unattended`, Opus, in `worktrees/<repo>/<slug>` (as today) | edit, validate, commit, push its branch, open the PR, ask in the inbox | merge, `make`, `docker compose`, edit `agents/runner.toml` or `agents/settings/*` |
| **Validation** | `claude -p /review-pr <repo> <pr> --unattended` (new command), fresh session, read-only checkout of the PR head | run validate commands, read the diff, `gh pr review`/`gh pr comment`, drive Playwright on preprod as the dev test account | edit or push code, merge, deploy |

- The manager stays deterministic, so an empty queue costs nothing and merge/deploy decisions are auditable bash. The one judgment
  call it delegates is triage: when an item is `blocked` after 2 attempts, a short Sonnet "manager" run reads the logs and
  either re-queues it with a note or writes the user an inbox notice with a diagnosis. This is optional and lands in Part 6.
- **Order each tick** (one Claude run per tick at most): (1) upkeep: inbox replies, preprod status, merges;
  (2) a `review` PR on preprod with no preprod validation yet → **validator (preprod stage)**; (3) a `review` PR waiting for review →
  **validator (review stage)**; (4) a queued plan → **implementer**. Work in flight finishes before new work starts.
- **The validator runs only for `review` PRs** (user, 2026-10-19). `low` PRs go straight from the gate to the merge.
- **Validation has two stages**, and each writes a result file (`approve | changes | blocked`) plus a PR review:
  1. **Review stage**, right after the implementer reports `ready` on a `review` PR. The validator re-runs the repo's full validation, runs
     `/code-review` on the diff against the plan's Goal and Files, and checks the plan's tasks are ✅. `changes` re-queues the
     implementer, resuming its session with the review as the queue note. This costs an attempt, so a third failure goes to `blocked`.
     This also covers the backlog item "let the agent address review comments on its own PRs".
  2. **Preprod stage**, after the manager deploys the PR to preprod. The validator runs every Human test step it can automate
     (curl through Cloudflare, Playwright as the dev test account) and comments on the PR with a checklist of passed, failed and
     "left for you". A failure removes the PR from preprod, sends it back to the implementer, and frees the lock.
     Steps only a human can do ("left for you") don't block the merge: the manager sends them as one inbox notice, and they go
     to the repo's ROADMAP Manual steps (per the 2026-10-12 rule).
- **Merge rule (manager; user, 2026-10-19):** `low` tier (gate passes) + green CI → merge. `review` tier + green CI + validator
  `approve` in **both** stages → merge, then release preprod back to the base branch. Nobody merges by hand; deploying to prod is
  the only manual step. A merge deploys nothing, so the user's prod deploy is now the one human checkpoint (see D5, `make prod-changes`).
- The validator never sees the implementer's session. Its prompt is the plan, the PR diff and the validate output.

### D4. One folder layout for both repos
Rule: **`.claude/` holds only what Claude Code loads from fixed paths. Everything else agent-related lives in `agents/`.**
```
AGENTS.md                    repo map, validate commands, rules (auto-loaded; engineerfamily renames CLAUDE.md → AGENTS.md)
.claude/commands/            plan, implement, validate, ship, rca, schedule-build, review-pr (same text in both repos)
.claude/settings.json        interactive-session permissions
agents/ROADMAP.md            the one tracker for that repo
agents/plans/, plans/done/   specs
agents/DEPLOY.md             how that repo deploys (engineerfamily: from README.md "Deploys" and CLAUDE.md)
agents/runner.toml           the repo's runner config: base branch, merge method, validate cmds, risk patterns, preprod cmds
agents/settings/{implement,validate}.json, agents/mcp.json   headless permissions per role (were scripts/agent/settings.json, mcp.json)
```
- `scripts/agent/` goes away in Strelitzia. `agents/runner.toml` replaces the hard-coded values. TOML because `tomllib` is in
  Python 3.11's standard library and the runner stays stdlib-only. bash reads values with `agent-runner config get <repo> <key>`.
- The repos register with the runner in `~/.config/agent-runner/repos/<name>.env` (`AGENT_REPO=<dev clone>`). The runner reads
  `agents/runner.toml` from `origin/<base>`, not from the dev clone's working tree.
- Each repo keeps its own `.claude/commands`. The PIV commands are mostly the same text in both, so drift is a risk:
  `agent-runner check-commands <repo>…` lists the differences, and the user decides whether they matter.
- `gate.py`'s `HIGH_RISK` in each repo includes `agents/runner.toml`, `agents/settings/*`, `.claude/settings.json` and `.github/*`.

### D5. engineerfamily-specific gates (`engineerfamily/agents/runner.toml`)
- `base = "main"`, `merge = "merge"` (keeps the repo's merge commits).
- `validate = "scripts/validate.sh"`. Part 3 adds it: `docker compose … config -q` for local, preprod and prod with
  `--env-file .env.template` (CI has no `/srv` `.env`), `nginx -t` in `nginx:alpine` for each `nginx.<env>.conf` (stub cert and
  `.htpasswd` files if needed), and the runner tests. `.github/workflows/ci.yml` runs the same, so `gh pr checks` has something to go green on.
- `high_risk` = `services/nginx/*`, `docker-compose*.yml`, `Makefile`, `scripts/*`, `services/*/Dockerfile`, `.github/*`,
  `*htpasswd*`, `.env*`, plus the D4 list. In practice only docs and `services/app`/`services/strelitzia` content changes can be `low`;
  everything else gets the validator and a preprod run before it merges.
- Preprod: `deploy = "make -C /srv/engineerfamily-preprod preprod-deploy ref={sha}"` (the PR head sha from the lock; `preprod-deploy`
  fetches all branches, so `agent/<slug>` is there). `release = "make -C /srv/engineerfamily-preprod preprod-deploy"` (back to `origin/main`).
  `health` = curl **through Cloudflare** with the netrc: `https://preprod.engineerfamily.net/` → 200,
  `/strelitzia/` → 200, `/strelitzia/dashboard/api/health` → `"ok": true` (a `127.0.0.1:8080` check doesn't prove host routing).
- Strelitzia's preprod commands are today's `PREPROD_DEPLOY_CMD`/`SEED_CMD`/`HEALTH_URL`, moved into its `runner.toml`.
- **Prod stays manual, enforced three ways:**
  1. Neither agent settings file allows `make`, `docker compose`, `gh workflow`, `git tag` or `git push` of tags; all are denied.
  2. `config.py` refuses a `runner.toml` whose preprod commands mention `deploy-prod`, `tag-prod`, `strelitzia-deploy`, `/srv/*-prod` or `-p engineerfamily ` (the prod project).
  3. The runner never calls a release target. Merging to `main`/`trunk` deploys nothing in either repo.
- **Prod checkpoint.** Agents now merge `review` PRs too, so the user should see what a prod deploy will ship. Part 3 adds
  `make prod-changes` to engineerfamily: it prints `git log` of `origin/main` since the last `v*` tag, and of Strelitzia `origin/trunk`
  since the commit `/srv/Strelitzia-prod` is on, each with PR links.

## Parts (each becomes its own plan via `/plan`; all `review`)
| Part | Repo | What | Runs |
|---|---|---|---|
| 0 create repo | GitHub | `gh repo create SiddharthEngineer/agent-runner --private`, seeded with today's `scripts/agent/*` and `tests/test_agent_runner.py` (history not kept; the Strelitzia history stays there) | manual (user) |
| 1 `runner-shared-1-core` | agent-runner | `config.py` + `runner.toml` loading, `<repo>/<slug>` keys with bare-slug migration, a repo column in the preprod lock, `~/.config/agent-runner` with fallback, per-repo gate patterns, the single merge rule, `AGENT_DRY_RUN`, the `agent-runner` CLI and `install.sh`, CI. Not in cron yet | interactive (the old runner can only build in Strelitzia) |
| 2 `runner-shared-2-roles` | agent-runner | Validator role: `/review-pr` template, result file and stages in `run.sh`, tick order, re-queue on `changes`, "left for you" notice | interactive |
| 3 `engineerfamily-agents-layout` | engineerfamily | `AGENTS.md` (from `CLAUDE.md`), `agents/{ROADMAP,DEPLOY}.md`, `agents/runner.toml`, `agents/settings/*`, `scripts/validate.sh`, `ci.yml`, `.claude/commands/*`, `.claude/settings.json`, `make prod-changes` | interactive (`.github/`, settings) |
| 4 `strelitzia-agents-layout` | Strelitzia | `agents/runner.toml`, `agents/settings/*`, `agents/mcp.json`; commands call `agent-runner …`; `/schedule-build` passes `--repo`; delete `scripts/agent/` and its tests **after** cutover; `HIGH_RISK` and `AGENTS.md` updated | unattended, last task after cutover |
| 5 cutover | VPS | Rollout steps 3–6 | manual (user) |
| 6 `runner-shared-3-triage` (optional) | agent-runner | Sonnet manager triage of `blocked` items | unattended |

## Rollout (the Strelitzia runner keeps working at every step)
1. **Parts 0–3 build next to the old runner.** Nothing the old runner reads changes: `~/src/Strelitzia/scripts/agent/`,
   `~/.config/strelitzia-agent/` and `~/.local/state/strelitzia-agent/` all stay as they are. The new code uses its own state dir
   and isn't in cron. Run Parts 1–3 interactively: the old runner only makes worktrees of Strelitzia.
2. **Dry run.** `AGENT_DRY_RUN=1 ~/.local/share/agent-runner/current/run.sh` (Part 1 adds it: it logs the decision, then exits before `claude`/`gh pr merge`/preprod)
   against a **copy** of the old `queue.json` in a temp state dir. Expected result: bare keys read as `strelitzia/*`, every item `done`, "nothing due".
3. **Drain.** `buildqueue.py list` on the old runner shows nothing `queued`, `running` or `on-preprod`, and `preprod.sh status` says `free`.
   (True at plan time.) Comment out the old cron line if it is on.
4. **Move config and state (user).** Copy `~/.config/strelitzia-agent/{env,preprod.netrc}` to `~/.config/agent-runner/`, and split
   the per-repo lines into `repos/strelitzia.env`. Add `machine preprod.engineerfamily.net` to the netrc (mode 600). Copy
   `queue.json` and `runs.jsonl` into `~/.local/state/agent-runner/`. Keep the old dirs until step 7.
5. **Install.** `agent-runner/install.sh <tag>`, then replace the crontab line with the new path (D1). Watch `runs.log` for two ticks.
6. **Smoke test, one per repo.** Queue a `low` docs-only plan in each repo. Expected for each: implementer PR → merged after green CI,
   with no validator run. Then queue a `review` engineerfamily plan that changes one nginx comment. Expected: validator review →
   preprod deploy through `make preprod-deploy ref=<sha>` → preprod-stage checklist comment → validator approves → the manager merges →
   the lock releases → preprod is back on `main`.
7. **Clean up** after a week with no problems: run Part 4's last task (delete Strelitzia's `scripts/agent/`), delete `~/.config/strelitzia-agent`
   and `~/.local/state/strelitzia-agent`, and drop the config-dir fallback.

Rollback at any step before 7: restore the old crontab line. The old code, config and state are untouched until then.

## Questions
Answered (user, 2026-10-19):
- Runner location: its own repo, `agent-runner`. Each repo keeps its own `.claude/` and `agents/`.
- The validator (both stages) runs only for `review` PRs.
- `low` PRs auto-merge. `review` PRs merge after the validator approves. Deploying to prod is the only manual step.
- engineerfamily "gate-only" is moot: with one merge rule there is no per-repo merge policy.

Open:
- D2: submodule in both repos, or one installed copy that both repos call (recommended)?

## Validation (of the finished rollout)
- engineerfamily `scripts/validate.sh` and CI pass on `main`. `agent-runner` CI passes, including the migration tests
  (bare keys, 3-column lock), the merge-rule tests and the prod-command guard.
- `crontab -l` has exactly one runner line, pointing at `~/.local/share/agent-runner/current`.
- Rollout step 6 passes in both repos, and `runs.log` shows each role starting and ending once per item.

## Human test steps
- Rollout steps 2–6, done by the user on the VPS.
