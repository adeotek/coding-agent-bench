# coding-agent-bench

Compare coding agents — **[moca](https://github.com/adeotek/moca)**, **OpenCode**, **Pi**, and **Claude Code** — on the same tasks, using [**Terminal-Bench 2.0**](https://www.tbench.ai/) through [**Harbor**](https://github.com/harbor-framework/harbor), the evaluation framework from the Terminal-Bench team.

Harbor runs every trial in a Docker container: it installs the agent CLI *inside* the task environment, hands it the task instruction, and scores the result with the task's own verifier. All four agents therefore run under identical task conditions, and the scores are comparable to the public Terminal-Bench leaderboard.

- **moca, OpenCode, Pi** run the same model (`opencode-go/deepseek-v4.1-flash` by default, via the OpenCode zen key).
- **Claude Code** runs its own Anthropic model (it cannot use a zen key) — same tasks, same sandbox, different model. That's accepted by design.
- Everything is pinned and re-runnable: Harbor version, moca release, dataset version, and the rendered job config are all recorded.

## Layout

```
agents/moca.py          Harbor integration (BaseInstalledAgent) for moca
agents/opencode_v2.py   Harbor integration for OpenCode v2 (@opencode/cli)
scripts/bench.sh        main entry point (setup | doctor | probe | dry-run | run | view | prune)
scripts/render_config.py renders the effective Harbor JobConfig JSON per profile
scripts/bench_report.py re-derives the report tables from results/jobs
scripts/probe-auth.sh   live 1-token credential probes (local binaries, scratch state)
docs/moca-bench-report.md    every moca run, cross-version, with the next-release actions
docs/agents-bench-report.md  moca vs Claude Code vs OpenCode vs Pi
Makefile                thin wrappers around bench.sh (make help)
results/                job results + rendered configs (gitignored)
.env                    your credentials + run knobs (gitignored)
```

Two integrations are custom because the upstream packages moved ahead of Harbor 0.24.0:
`agents/moca.py` (moca is not pre-integrated) and `agents/opencode_v2.py` (Harbor's
built-in `opencode` agent drives v1: the v2 npm package is `@opencode/cli`, not
`opencode-ai`, and v2 moved `--model` onto `run` — the subclass overrides install and
the run command, everything else is inherited).

## Prerequisites

- **Docker** — daemon running, your user in the `docker` group. Terminal-Bench images are GBs: keep **≥15–20 GB free on the Docker root** (`make doctor` reports it).
- **uv** — https://docs.astral.sh/uv/ (used to install Harbor as a tool).
- **python3 ≥ 3.11** (stdlib only; used by the config renderer).
- **Credentials** (see next section).

## Credentials

Put them in `.env` (`cp .env.example .env`; it is gitignored):

| Agent(s) | Variable | Where to get it |
|---|---|---|
| moca, OpenCode, Pi | `OPENCODE_API_KEY` | your OpenCode zen key (same key as `~/projects/moca/.env`), used for the `opencode-go` tier |
| Claude Code | `ANTHROPIC_API_KEY` **or** `CLAUDE_CODE_OAUTH_TOKEN` | an Anthropic API key; or a subscription token from `claude setup-token` (1-year, headless-friendly) |

How credentials reach the containers:

- **moca** — the adapter writes a minimal `~/.config/moca/config.jsonc` that references the key as `env:OPENCODE_API_KEY` (the key is never written to disk). The value is delivered in Harbor's agent phase via `--ae OPENCODE_API_KEY=…`, which `bench.sh` adds automatically.
- **OpenCode / Pi** — same mechanism, same variable: the provider-dependent agents get the credential for the model selected with `-m`.
- **Claude Code** — Harbor auto-forwards `ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN` from the process environment during that agent's phase only.

One name, deliberately: `OPENCODE_API_KEY` is moca's own built-in default for the `opencode-go` provider, so all three zen agents read the same variable. The old `OPENCODE_GO_KEY` name is still accepted by `bench.sh` with a deprecation warning (rename it in `.env`).

(Note: `--ae` values appear transiently in the local process's argv. The `.env` file itself is never handed to Harbor, and keys are never written into the rendered config.)

## Setup (one time)

```bash
cd ~/projects/coding-agent-bench
make setup          # installs Harbor (pinned 0.24.0) and checks Docker
cp .env.example .env  # then edit .env and fill in the credentials
make doctor         # docker + harbor + moca adapter import + credential presence
make test           # harness unit test: the moca run line + session mirror (no spend)
```

Optional but recommended — one live request per agent (~cents) proving the exact credential flow:

```bash
make probe          # or: make doctor ARGS=--probe
```

## Running

### 1. Smoke (first time; a few minutes, ~cents)

```bash
make smoke          # hello-world task, all agents — full pipeline test
make smoke AGENTS=moca,opencode   # limit the agents (AGENTS is a .env knob / env var)
```

This pulls a small task image, installs each agent CLI inside the container, runs one trivial task, and verifies it. If this passes, the machinery works.

### 2. Subset (recommended for iteration)

```bash
make subset         # terminal-bench@2.0, first N_TASKS tasks (default 20) × 4 agents = 80 trials
```

- Runs for **hours**, not minutes: expect several hours with `N_CONCURRENT=2` on a 6-core box.
- API cost is real: budget a couple of dollars to low tens of dollars per sweep for the zen models, more for Claude. Raise `N_ATTEMPTS` (e.g. 3) only after the pipeline is proven.
- Prefer a **fixed task list** for comparability across runs:

  ```bash
  TASK_NAMES=task-a,task-b,task-c make subset   # .env knob, same effect
  ```

### 3. Full Terminal-Bench 2.0

```bash
make full           # whole dataset (100+ tasks) × 4 agents — expensive: hours, GBs of images
```

### Viewing results

```bash
make view           # Harbor's web viewer over results/jobs (localhost only)
make net-view       # same viewer bound to 0.0.0.0 (network access — mind your firewall; the viewer is unauthenticated)
```

Job outputs live under `results/jobs/<job-name>/`: per-trial agent logs (`agent/moca.txt`, `agent/moca-session.jsonl`, `opencode.txt`, `pi.txt`, `claude-code.txt`), verifier output, and reward. Handy extras: `harbor job list`, `harbor analyze <job>`.

moca's token/cost usage is backfilled by the adapter from its session JSONL, so the viewer and job metrics show it next to the other agents.

## Knobs (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `ZEN_MODEL` | `opencode-go/deepseek-v4.1-flash` | model for moca + OpenCode + Pi |
| `CLAUDE_MODEL` | `anthropic/claude-sonnet-5` | model for Claude Code |
| `MOCA_VERSION` | `v0.7.9` | pinned moca release package |
| `MOCA_MAX_STEPS` | `100` | moca `context.maxSteps` (moca's own default is 40; limits are reported) |
| `MOCA_MODE` | `yolo` | moca permission mode, rendered into the job config (v0.7.2 made `auto` moca's default) |
| `OPENCODE_VERSION` | `2.1.4` | pinned OpenCode release (npm `@opencode/cli`) |
| `PI_VERSION` | `1.4.0` | pinned Pi release (npm `@earendil-works/pi-coding-agent`) |
| `CLAUDE_VERSION` | `2.1.310` | pinned Claude Code release (npm) |
| `N_TASKS` | `20` | subset size |
| `TASK_NAMES` | — | comma-separated task names (overrides `N_TASKS`) |
| `N_CONCURRENT` | `2` | concurrent trials (raise on a bigger machine) |
| `N_ATTEMPTS` | `1` | attempts per task × agent (raise for variance estimates) |
| `AGENTS` | all four | comma-separated subset |
| `JOBS_DIR` | `results/jobs` | where job results go |
| `HARBOR_VERSION` | `0.24.0` | Harbor pin |

Anything the wrapper doesn't expose can be passed straight through to Harbor:

```bash
./scripts/bench.sh run subset --n-concurrent 4 --max-retries 1
```

## Reproducibility

- **Harbor**: pinned by `HARBOR_VERSION` (`make setup` installs exactly that).
- **moca**: pinned by `MOCA_VERSION` (release tarball, sha256-verified against the release's `checksums.txt`).
- **Dataset**: `TB_VERSION=2.0` (use `TASK_NAMES` for exact task sets; Harbor caches task copies). The 12-task benchmark set is checked in as `docs/tb2-subset-12.txt` — `TASK_NAMES=$(tr '\n' ',' < docs/tb2-subset-12.txt | sed 's/,$//')` (it lives in the repo so it can't be lost to a scratch-dir sweep).
- **Agents**: all four are pinned — moca `MOCA_VERSION` (release tarball, sha256-verified), OpenCode `OPENCODE_VERSION` (npm `@opencode/cli`), Pi `PI_VERSION` (npm `@earendil-works/pi-coding-agent`) and Claude Code `CLAUDE_VERSION` (npm). `MOCA_MAX_STEPS` and `MOCA_MODE` record moca's step budget and permission stance. All agents accept `--ak version=…`; values must be valid for that tool's package manager.
- The rendered effective config is saved to `results/effective-<profile>.json` (refreshed for inspection) and copied into each job directory, so every run records exactly what ran. A `run` renders to a per-run `results/effective-<profile>-<timestamp>-<pid>.json` and hands *that* path to Harbor, so two concurrent runs cannot pick up each other's config between render and exec (the canonical name is only a convenience copy).

## Extending

- **Another pre-integrated agent** (e.g. `codex`, `gemini-cli`, `aider` — see `harbor run --help`): add an entry in `agents()` in `scripts/render_config.py`, add its credentials to `agent_env_args()` in `scripts/bench.sh` if it isn't auto-forwarded, run `make doctor` + `make dry-run`.
- **Another custom agent**: copy `agents/moca.py` as a template (it shows install-from-release, config writing, log capture, and metrics backfill), register the import path (`agents.<name>:<Class>`) in `render_config.py`.
- **Your own tasks/datasets**: Harbor supports local task dirs, Git-task repos, and custom registries — point a `tasks:`/`datasets:` entry at them (schema: `harbor job schema`; docs: https://docs.harborframework.com/tasks/overview).
- **New profile** (e.g. a curated 5-task set): add a branch in `build()` in `scripts/render_config.py` or just use `TASK_NAMES`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Agent fails auth inside the container | `make probe` first — it validates the credential flow locally. moca/OpenCode/Pi need `OPENCODE_API_KEY`; Claude Code needs `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`. |
| OpenCode fails to call `opencode-go` | The adapter relies on `OPENCODE_API_KEY`. Debug lever: `--ak opencode_config='{"provider":{"opencode-go":{"options":{"apiKey":"{env:OPENCODE_API_KEY}"}}}}'` (OpenCode supports `{env:…}` config interpolation). |
| Docker out of disk (TB2 images are GBs) | `make prune` between runs; check free space with `make doctor`. |
| `permission denied` on docker | `sudo usermod -aG docker $USER` + re-login. |
| Harbor behaving oddly after an upgrade | Keep the pin: bump `HARBOR_VERSION` in `.env`, then `uv tool uninstall harbor && make setup`. |
| Job failed halfway / rate limits | Re-run; Harbor resumes what's cached. Add `--max-retries 1` for transient API errors. |
| Two legs launched in the same second | Handled: `run` passes a unique `--job-name` because Harbor names job directories by second — without it one leg dies instantly with `Job directory … already exists and cannot be resumed with a different config`. |
| Harbor hangs in `Collecting main service artifacts` after an agent-phase timeout | The trial's files are already complete on disk (`agent/moca-session.jsonl`, `agent/moca.txt`, `exception.txt`, `verifier/`): kill the harbor process and read them — a leg stuck there does not finish on its own. |

## Reports

Two tracking reports are the benchmark's artifact. Both are re-derived from `results/jobs/` (never from each other's prose) and both are updated after **every** run:

| Report | Covers | Ends with |
|---|---|---|
| [`docs/moca-bench-report.md`](docs/moca-bench-report.md) | every moca run on the fixed 12-task subset + the cell diagnostics | a summary: how the latest moca compares with all previous releases, the open issues, and the actions proposed for the next release |
| [`docs/agents-bench-report.md`](docs/agents-bench-report.md) | moca vs Claude Code vs OpenCode vs Pi | the cross-agent verdict and the per-agent failure taxonomy |

Update procedure (in the same commit as the run):

```bash
python3 scripts/bench_report.py runs                  # one line per job
python3 scripts/bench_report.py summary <job>         # per-agent cost/token/speed
python3 scripts/bench_report.py matrix <job> <job>    # task × job pass matrix
```

Add the row (moca report) or the column (agents report), re-derive the matrix, write the per-cell diagnosis, then refresh the summary section — a scoreboard that argues with its own table is worse than no scoreboard.

## Status & history

Current pins (see [Knobs](#knobs-env)): Harbor 0.24.0 · moca v0.7.9 · OpenCode 2.1.4 · Pi 1.4.0 · Claude Code 2.1.310 · dataset `terminal-bench@2.0` with the checked-in 12-task subset.

- `make doctor` validates docker, Harbor, the adapter import (with its default pin and key variable) and credential presence; it also reads the provider's `/models` catalog and warns when `ZEN_MODEL` is not listed there — moca ≥ v0.7.10 validates the configured model against its discovered list, so a retired id must be caught before a sweep, not during one.
- `--dry-run` passes both profiles (smoke = 4 trials; subset with `docs/tb2-subset-12.txt` = 48 trials).
- The last four-agent in-container hello-world smoke (2026-10-16, moca v0.5.1-beta / OpenCode 2.0.30 / Pi 1.3.0 / Claude Code 2.1.301) scored 4/4 reward 1.0 with every version confirmed in `result.json`. The pins have moved since — run `make smoke` before the next sweep.
- Historical one-off reports keep their forensic detail: [2026-10-11](docs/bench-2026-10-11-moca-claude-code-pi.md) and [2026-10-16](docs/bench-2026-10-16-moca-claude-code-pi-opencode.md). Both are superseded by the tracking reports above.

## References

- Harbor docs — https://docs.harborframework.com
- Terminal-Bench — https://www.tbench.ai (leaderboard: https://www.tbench.ai/leaderboard/terminal-bench/2.0)
- Custom agents guide — https://docs.harborframework.com/agents/custom-agents
- Uploading to the Hub: `harbor upload results/jobs/<job>`. Harbor masks agent-env values in stored configs (verified on 0.24.0: `oc_s****ifJ`), and masks can keep a short prefix/suffix — review the job directory before sharing, or pass secrets at launch time (`--launch --one-off-secret`) instead of by `--ae`.
