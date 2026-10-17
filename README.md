# coding-agent-bench

Compare coding agents — **[moca](https://github.com/adeotek/moca)**, **OpenCode**, **Pi**, and **Claude Code** — on the same tasks, using [**Terminal-Bench 2.0**](https://www.tbench.ai/) through [**Harbor**](https://github.com/harbor-framework/harbor), the evaluation framework from the Terminal-Bench team.

Harbor runs every trial in a Docker container: it installs the agent CLI *inside* the task environment, hands it the task instruction, and scores the result with the task's own verifier. All four agents therefore run under identical task conditions, and the scores are comparable to the public Terminal-Bench leaderboard.

- **moca, OpenCode, Pi** run the same model (`opencode-go/glm-5.3-flash` by default, via the OpenCode zen key).
- **Claude Code** runs its own Anthropic model (it cannot use a zen key) — same tasks, same sandbox, different model. That's accepted by design.
- Everything is pinned and re-runnable: Harbor version, moca release, dataset version, and the rendered job config are all recorded.

## Layout

```
agents/moca.py          Harbor integration (BaseInstalledAgent) for moca
agents/opencode_v2.py   Harbor integration for OpenCode v2 (@opencode/cli)
scripts/bench.sh        main entry point (setup | doctor | probe | dry-run | run | view | prune)
scripts/render_config.py renders the effective Harbor JobConfig JSON per profile
scripts/probe-auth.sh   live 1-token credential probes (local binaries, scratch state)
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
| moca, OpenCode, Pi | `OPENCODE_GO_KEY` | your OpenCode zen key (same key as `~/projects/moca/.env`), used for the `opencode-go` tier |
| Claude Code | `ANTHROPIC_API_KEY` **or** `CLAUDE_CODE_OAUTH_TOKEN` | an Anthropic API key; or a subscription token from `claude setup-token` (1-year, headless-friendly) |

How credentials reach the containers:

- **moca** — the adapter writes a minimal `~/.config/moca/config.jsonc` that references the key as `env:OPENCODE_GO_KEY` (the key is never written to disk). The value is delivered in Harbor's agent phase via `--ae OPENCODE_GO_KEY=…`, which `bench.sh` adds automatically.
- **OpenCode / Pi** — same mechanism via `--ae OPENCODE_API_KEY=…` (the provider-dependent agents get the credential for the model selected with `-m`).
- **Claude Code** — Harbor auto-forwards `ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN` from the process environment during that agent's phase only.

(Note: `--ae` values appear transiently in the local process's argv. The `.env` file itself is never handed to Harbor, and keys are never written into the rendered config.)

## Setup (one time)

```bash
cd ~/projects/coding-agent-bench
make setup          # installs Harbor (pinned 0.24.0) and checks Docker
cp .env.example .env  # then edit .env and fill in the credentials
make doctor         # docker + harbor + moca adapter import + credential presence
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
| `ZEN_MODEL` | `opencode-go/glm-5.3-flash` | model for moca + OpenCode + Pi |
| `CLAUDE_MODEL` | `anthropic/claude-sonnet-5` | model for Claude Code |
| `MOCA_VERSION` | `v0.6.3` | pinned moca release package |
| `MOCA_MAX_STEPS` | `100` | moca `context.maxSteps` (moca's own default is 40; limits are reported) |
| `OPENCODE_VERSION` | `2.0.30` | pinned OpenCode release (npm `@opencode/cli`) |
| `PI_VERSION` | `1.3.0` | pinned Pi release (npm) |
| `CLAUDE_VERSION` | `2.1.301` | pinned Claude Code release (npm) |
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
- **Dataset**: `TB_VERSION=2.0` (use `TASK_NAMES` for exact task sets; Harbor caches task copies).
- **Agents**: all four are pinned — moca `MOCA_VERSION` (release tarball, sha256-verified), OpenCode `OPENCODE_VERSION` (npm `@opencode/cli`), Pi `PI_VERSION` and Claude Code `CLAUDE_VERSION` (npm). `MOCA_MAX_STEPS` records moca's step budget. All agents accept `--ak version=…`; values must be valid for that tool's package manager.
- The rendered effective config is saved to `results/effective-<profile>.json` and copied into each job directory, so every run records exactly what ran.

## Extending

- **Another pre-integrated agent** (e.g. `codex`, `gemini-cli`, `aider` — see `harbor run --help`): add an entry in `agents()` in `scripts/render_config.py`, add its credentials to `agent_env_args()` in `scripts/bench.sh` if it isn't auto-forwarded, run `make doctor` + `make dry-run`.
- **Another custom agent**: copy `agents/moca.py` as a template (it shows install-from-release, config writing, log capture, and metrics backfill), register the import path (`agents.<name>:<Class>`) in `render_config.py`.
- **Your own tasks/datasets**: Harbor supports local task dirs, Git-task repos, and custom registries — point a `tasks:`/`datasets:` entry at them (schema: `harbor job schema`; docs: https://docs.harborframework.com/tasks/overview).
- **New profile** (e.g. a curated 5-task set): add a branch in `build()` in `scripts/render_config.py` or just use `TASK_NAMES`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Agent fails auth inside the container | `make probe` first — it validates the credential flow locally. moca/OpenCode/Pi need `OPENCODE_GO_KEY`; Claude Code needs `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`. |
| OpenCode fails to call `opencode-go` | The adapter relies on `OPENCODE_API_KEY`. Debug lever: `--ak opencode_config='{"provider":{"opencode-go":{"options":{"apiKey":"{env:OPENCODE_API_KEY}"}}}}'` (OpenCode supports `{env:…}` config interpolation). |
| Docker out of disk (TB2 images are GBs) | `make prune` between runs; check free space with `make doctor`. |
| `permission denied` on docker | `sudo usermod -aG docker $USER` + re-login. |
| Harbor behaving oddly after an upgrade | Keep the pin: bump `HARBOR_VERSION` in `.env`, then `uv tool uninstall harbor && make setup`. |
| Job failed halfway / rate limits | Re-run; Harbor resumes what's cached. Add `--max-retries 1` for transient API errors. |

## Verified status (2026-10-10 → 2026-10-17, this host)

- Harbor 0.24.0 installed via uv; Docker 29.9.1; both custom adapters (`agents/moca.py`, `agents/opencode_v2.py`) import cleanly against Harbor's own environment.
- `--dry-run` passes both profiles: smoke = 4 trials; subset = 80 trials (20 tasks × 4 agents).
- Live credential probes (local binaries, scratch state): moca ✅, OpenCode ✅, Pi ✅, Claude Code ✅ (re-run 2026-10-16 on the new pins — all four exercised).
- **Hello-world smoke, in-container, end to end** (see `results/jobs/cab-smoke-*`): moca ✅, OpenCode ✅, Pi ✅, Claude Code ✅ — all reward 1.0.
  - moca: 32 s; 7,239 in / 59 out tokens; $0.0011 — usage backfilled into the trial result by the adapter (`agent_result` in the trial's `result.json`).
  - OpenCode / Pi / Claude Code: reward 1.0 as well. Re-verified 2026-10-16 with moca v0.5.1-beta, OpenCode v2.0.30 (`@opencode/cli`), Pi 1.3.0, Claude Code 2.1.301 — 4/4 again, versions and metrics confirmed in `result.json`.
- **First subset run (2026-10-11)** — 12 curated TB2 tasks × moca/Claude Code/Pi (36 trials, ~1h31m, $0.62 zen + $0 cash): solved 10/12, 11/12, 9/12 — report and full analysis: `docs/bench-2026-10-11-moca-claude-code-pi.md`.
- **Second subset run (2026-10-16)** — first 4-agent run, same 12 tasks, latest pins, moca `maxSteps=100` (48 trials, 2h03m, $1.13 zen + $0 cash): solved pi 11/12, opencode 10/12, claude-code 10/12, moca 6/12 — report: `docs/bench-2026-10-16-moca-claude-code-pi-opencode.md`.
- **moca v0.6.0 follow-up (2026-10-17)** — moca only, same 12-task subset + a 9-task diagnostic (73 min combined, $0.49): diagnostic 6/9 (6/8 on the original 8-task set, up from 3/8), subset **7/12** (up from 6/12; $0.044/solved) — follow-up section of the 2026-10-16 report. Every request ran at `effort=low` (the flash serving variant accepts only `low|high|max`; v0.6.0 clamps), and the trial sessions confirm the adapter's exit-3/metrics contract on the new version.
- **moca v0.6.1 round 3 (2026-10-17)** — moca only, same 12-task subset (25 min, **$0.18**, 4.20M tokens): subset **10/12** (up from 7/12; $0.018/solved — best moca result since v0.3.0 and one convertible cell from the field's best 11/12). The shell-level stateful-file guard fired on the wire and converted `db-wal-recovery`; `build-cython-ext` and `nginx-request-logging` converted too, no regressions. `mailman` root-caused (the agent set `SubscriptionPolicy.open`, which suppresses the confirmation mail the task's stated behaviour requires) and `filter-js-from-html` audited as a task-side contradiction (0 passes in 10 attempts across four agents — the prose demands byte preservation while the hidden test requires BeautifulSoup re-serialisation) — follow-up 2 section of the 2026-10-16 report.

## References

- Harbor docs — https://docs.harborframework.com
- Terminal-Bench — https://www.tbench.ai (leaderboard: https://www.tbench.ai/leaderboard/terminal-bench/2.0)
- Custom agents guide — https://docs.harborframework.com/agents/custom-agents
- Uploading to the Hub: `harbor upload results/jobs/<job>`. Harbor masks agent-env values in stored configs (verified on 0.24.0: `oc_s****ifJ`), and masks can keep a short prefix/suffix — review the job directory before sharing, or pass secrets at launch time (`--launch --one-off-secret`) instead of by `--ae`.
