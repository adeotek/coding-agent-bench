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
scripts/bench_report.py re-derives the report tables from results/jobs (runs|summary|matrix|steps|compare|json)
scripts/probe-auth.sh   live 1-token credential probes (local binaries, scratch state)
test/                   unit tests for the moca run line and the report parsers (make test)
docs/tb2-subset-12.txt       the fixed 12-task subset every comparison uses
docs/tb2-subset-24.txt       the comparison set: the fixed 12 + 12 cells moca cannot pass cheaply
docs/tb2-screen.txt          the 77 never-run tasks, ordered cheap-first (make screen BATCH=N)
docs/moca-bench-report.md    every moca run, cross-version, with the next-release actions
docs/agents-bench-report.md  moca vs Claude Code vs OpenCode vs Pi
Makefile                thin wrappers around bench.sh (make help)
results/                job results + rendered configs (gitignored)
.env                    your credentials + run knobs (gitignored)
```

Two integrations are custom because the upstream packages moved ahead of Harbor 0.25.0:
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
make setup          # installs Harbor (pinned 0.25.0) and checks Docker
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

### 3. Screening new tasks (moca only)

The 12-task subset is saturated (11/12 for three of four agents, the one loss task-side), so
growth now comes from failures elsewhere, not from a bigger sample of the same 12.
`docs/tb2-screen.txt` lists the 77 terminal-bench 2.0 tasks this bench has never run, ordered
cheap-first; `docs/tb2-screen-batch-1.txt` is the first 10.

```bash
make screen              # batch 1: moca only, 1 attempt, ~$0.20 of zen spend
make screen BATCH=3      # next 10-task batch
make prune               # between batches — task images are GB-sized
scripts/bench_report.py steps cab-subset-<stamp>   # turns/tools/tokens per trial
```

Read the result as a **failure corpus**, not a score: the value is in the cells moca drops and
in how many turns it spends failing. `steps` reports turns (one model response plus its tool
calls), tool calls, tokens/turn and proximity to `MOCA_MAX_STEPS`, so a failure can be
classified as budget exhaustion, a tool loop, context growth, or a plain wrong answer.

The 2026-10-25 sweep (batches 1–3, 30 tasks, 25/30, $0.43) is written up in
[`docs/moca-bench-report.md`](docs/moca-bench-report.md#screening-sweep--2026-10-25-the-tasks-this-bench-had-never-run-moca-only).
Its five failures plus seven grinding passes became the second half of
`docs/tb2-subset-24.txt` — the set to compare releases on, because the 12-task one is saturated.
That set has now been run twice with all four agents (`AGENTS= N_ATTEMPTS=1 TASK_NAMES=$(grep -v '^#' docs/tb2-subset-24.txt | paste -sd,)`);
one cell in seven disagrees between the two runs, so a cell-level conclusion needs a 3-attempt
cell run (`N_ATTEMPTS=3 TASK_NAMES=…`) before anyone writes a fix against it.

### 4. Full Terminal-Bench 2.0

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
| `MOCA_VERSION` | `v0.7.12` | pinned moca release package |
| `MOCA_MAX_STEPS` | `250` | moca `context.maxSteps` (moca's own default is 40; limits are reported) |
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
| `HARBOR_VERSION` | `0.25.0` | Harbor pin — `run`/`dry-run` refuse to start on any other installed version |
| `HARBOR_PYTHON` | `3.14` | Interpreter `setup` builds the Harbor tool env with — the highest release with full wheel coverage (uv defaults to the newest Python; 3.15 cannot build `fastuuid`, and a failed install leaves no `harbor` binary at all) |

Anything the wrapper doesn't expose can be passed straight through to Harbor:

```bash
./scripts/bench.sh run subset --n-concurrent 4 --max-retries 1
```

## Reproducibility

- **Harbor**: pinned by `HARBOR_VERSION`. `make setup` installs exactly that version with `--python $HARBOR_PYTHON`, and `scripts/bench.sh run|dry-run` **hard-fail** when the installed version differs — `HARBOR_ALLOW_VERSION_MISMATCH=1` is the deliberate one-off override.
- **moca**: pinned by `MOCA_VERSION` (release tarball, sha256-verified against the release's `checksums.txt`).
- **Dataset**: `TB_VERSION=2.0` (use `TASK_NAMES` for exact task sets; Harbor caches task copies). The 12-task benchmark set is checked in as `docs/tb2-subset-12.txt` — `TASK_NAMES=$(tr '\n' ',' < docs/tb2-subset-12.txt | sed 's/,$//')` (it lives in the repo so it can't be lost to a scratch-dir sweep).
- **Agents**: all four are pinned — moca `MOCA_VERSION` (release tarball, sha256-verified), OpenCode `OPENCODE_VERSION` (npm `@opencode/cli`), Pi `PI_VERSION` (npm `@earendil-works/pi-coding-agent`) and Claude Code `CLAUDE_VERSION` (npm). `MOCA_MAX_STEPS` and `MOCA_MODE` record moca's step budget and permission stance. All agents accept `--ak version=…`; values must be valid for that tool's package manager.
- The rendered effective config is saved to `results/effective-<profile>.json` (refreshed for inspection) and copied into each job directory, so every run records exactly what ran. A `run` renders to a per-run `results/effective-<profile>-<timestamp>-<pid>.json` and hands *that* path to Harbor, so two concurrent runs cannot pick up each other's config between render and exec (the canonical name is only a convenience copy).

## Extending

- **Another pre-integrated agent** (e.g. `codex`, `gemini-cli`, `aider` — see `harbor run --help`): add an entry in `agents()` in `scripts/render_config.py`, add its credentials to `agent_env_args()` in `scripts/bench.sh` if it isn't auto-forwarded, run `make doctor` + `make dry-run`.
- **Another custom agent**: copy `agents/moca.py` as a template (it shows install-from-release, config writing, log capture, and metrics backfill), register the import path (`agents.<name>:<Class>`) in `render_config.py`.
- **Your own tasks/datasets**: Harbor supports local task dirs, Git-task repos, and custom registries — point a `tasks:`/`datasets:` entry at them (schema: `harbor job schema`; docs: https://docs.harborframework.com/tasks/overview).
- **New profile** (e.g. a curated 5-task set): add a branch in `build()` in `scripts/render_config.py` or just use `TASK_NAMES`.

## Sharding a run (why, and when)

Harbor keeps every image a job pulls for that job's lifetime. Uncompressed, the 89
Terminal-Bench 2.0 images are **~145 GB** (Docker Hub compressed sizes × the 2.6–4.0×
decompression ratio measured on images already pulled here), plus ~15 GB of container
scratch for four concurrent agents. A 96 GB host cannot run that as one job.

So a set can be measured in slices:

```bash
TASK_FILE=docs/tb2-all.txt make sharded PROFILE=full SHARDS=5   # s1of5 … s5of5, pruned between
```

Each shard is an ordinary job (`cab-<profile>-s<k>of<n>-<stamp>-<pid>`) with its own
manifest, so it is resumable: a shard that dies is re-run alone, and nothing already
measured is lost. Stitching is a *reading* operation — pass every shard job to
`report`/`compare` and the tasks are pooled:

```bash
python3 scripts/bench_report.py report $(ls -d results/jobs/cab-full-s*of5-* | xargs -n1 basename)
```

Three invariants keep that honest, and the test suite pins all three:

- **disjoint, ordered, covering** — `SHARD=k/n` takes a contiguous ceil-sized block, so
  the shards' union is exactly the parent list and no task is measured twice;
- **the parent fingerprint travels with the shard** — a shard's own task list cannot
  prove two jobs measured the same cells, so `manifest.shard.parent_task_list_sha256`
  records the whole list, and `comparable()` compares that;
- **the report says what it covers** — a stitched report prints `tasks covered: 71/89
  (2 uncovered)` and warns when shards come from different parents. A partial set never
  reads as a whole one.

`SHARD` needs an explicit list (`TASK_FILE` or `TASK_NAMES`); slicing an `n_tasks`
dataset would mean guessing which tasks Harbor picks, so the render refuses instead.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Agent fails auth inside the container | `make probe` first — it validates the credential flow locally. moca/OpenCode/Pi need `OPENCODE_API_KEY`; Claude Code needs `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`. |
| OpenCode fails to call `opencode-go` | The adapter relies on `OPENCODE_API_KEY`. Debug lever: `--ak opencode_config='{"provider":{"opencode-go":{"options":{"apiKey":"{env:OPENCODE_API_KEY}"}}}}'` (OpenCode supports `{env:…}` config interpolation). |
| Docker out of disk (TB2 images are GBs) | `make prune` between runs; check free space with `make doctor`. |
| `permission denied` on docker | `sudo usermod -aG docker $USER` + re-login. |
| `error: harbor X is installed but the pin is Y` | The guard working. `./scripts/bench.sh setup --force` reinstalls the pin (needs python `$HARBOR_PYTHON`). Do not bypass it to get a run started. |
| Harbor behaving oddly after an upgrade | Bump `HARBOR_VERSION` deliberately (`.env`), `./scripts/bench.sh setup --force`, then re-run the ladder — the adapters are written against one release, and 0.25 moved `ModelConnectionSpec` into `harbor.agents.agent_auth_resolution`. |
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
python3 scripts/bench_report.py steps <job>           # turns/tools/tokens per trial + step cap
python3 scripts/bench_report.py compare <job> <job>   # paired per-task deltas, CI, McNemar, flip rate
python3 scripts/bench_report.py credit <job>           # partial credit from verifier ctrf.json
python3 scripts/bench_report.py export <job>           # summary.json: trials + manifest + aggregates
python3 scripts/bench_report.py report <job> --out=docs/bench-latest.md   # generated tables
python3 scripts/bench_report.py diff <job> <task>      # why one cell went differently
make audit                                            # oracle/nop: is every task a task?
make sharded PROFILE=subset SHARDS=4                  # same set, N sequential jobs, images pruned between
SHARD=2/5 TASK_FILE=docs/tb2-all.txt make dry-run ARGS=full   # what one shard would run
python3 scripts/bench_report.py audit $(cat results/audit/jobs/*.job | sort -u)  # the findings

`compare` is the only command that makes a claim. Every agent runs the same
cells, so it pairs them **by task**: the delta is the mean per-task pass-rate
difference, the 95 % CI comes from resampling *tasks* (never trials — repeats in
one cell share its difficulty), and the exact McNemar p uses only the cells the
two agents disagree on. Give it the same job twice to get the **flip rate** — the
share of cells that change verdict between identical runs. A delta whose CI
includes zero is not a finding, whatever the point estimate says: at 24 tasks a
single cell is worth 4 points, so only a large, consistent difference clears the bar.
```

`make audit` runs Harbor's own `oracle` and `nop` agents over every tracked task
(`docs/tb2-all.txt`, 89 cells): oracle must pass — the reference solution works as
specified — and nop must fail, because doing nothing cannot satisfy the verifier.
Anything else is a **task-side finding**, and it costs zero tokens. The audit runs
in batches and drops each batch's images afterwards (Terminal-Bench images average
0.65 GB; the full set is ~58 GB and this host has ~22 GB free), keeping the 24-task
comparison set warm. `bench_report.py audit` classifies the result as
healthy / host-limited / broken-task / vacuous / both-broken / no-verdict — and `no-verdict` is
never folded into either side, since an infrastructure failure is not a task defect, while
host-limited (no `/dev/kvm`, a vCPU missing instructions) is a fact about the machine, not about
the task. The 2026-10 sweep: **78 healthy, 8 broken, 3 host-limited** — every cell and its
evidence in `docs/task-defects.md`.

### What may be measured: the run list

The audit is worthless if its verdicts don't change what gets run, so the lists are
**derived from it** — never hand-written:

```bash
make runlist        # → docs/tb2-measurable.txt (78 cells) + docs/tb2-watch.txt (11)
make audit-watch    # re-audit the broken cells, zero tokens; fixed ones return automatically
```

- `docs/tb2-measurable.txt` — cells whose own oracle passes **here**. This is the list a
  measured run should use (`TASK_FILE=docs/tb2-measurable.txt ./scripts/bench.sh run full`).
- `docs/tb2-watch.txt` — the cells that are not healthy, each with its class
  (`broken-task`, `host-limited`). Re-audit, never score.

`render_config.py` enforces the second half: a non-audit profile **drops** any cell on the
watch list and says so, by name, on stderr. A broken cell has no agent signal in either
direction — a loss is the task's fault and a win is noise — so scoring one is how you publish
a regression that never happened. `ALLOW_DEFECTIVE=1` keeps them (for investigating a cell);
the `audit` profile is exempt, since finding them is its job. The run lists are derived from
the job store, so a cell that gets repaired upstream returns the moment its oracle passes —
`make audit-watch` is that gate.

Nothing is hidden in the numbers either: reports print coverage (`78/89`), and
`docs/task-defects.md` lists every excluded cell with its evidence.

`credit` reads `verifier/ctrf.json` (already written by every trial) and scores
tests passed / tests run, skipping `skipped`. On the 24-task subset that is 82
tests instead of 24 cells, so it resolves ~3.4× finer — moca goes from 82.6 % to
95.0 % binary vs credit, because it usually fails one test of several. It is a
secondary metric: a task is still solved or not. `report` writes the whole
picture (run card from the manifest, leaderboard with CI + cost p50/p90, per-task
matrix, paired verdicts, flip rate) and **excludes cells listed in
`docs/task-side.json`** — every entry there carries its evidence, and
`--include-task-side` puts them back.


Add the row (moca report) or the column (agents report), re-derive the matrix, write the per-cell diagnosis, then refresh the summary section — a scoreboard that argues with its own table is worse than no scoreboard.

## Status & history

Current pins (see [Knobs](#knobs-env)): Harbor 0.25.0 · moca v0.7.12 · OpenCode 2.1.4 · Pi 1.4.0 · Claude Code 2.1.310 · dataset `terminal-bench@2.0` with the checked-in 12-task subset.

- `make doctor` validates docker, Harbor, the adapter import (with its default pin and key variable) and credential presence; it also reads the provider's `/models` catalog and warns when `ZEN_MODEL` is not listed there — moca ≥ v0.7.10 validates the configured model against its discovered list, so a retired id must be caught before a sweep, not during one.
- `--dry-run` passes both profiles (smoke = 4 trials; subset with `docs/tb2-subset-12.txt` = 48 trials).
- The newest four-agent sweep is **2026-10-25** at the current pins (moca v0.7.10 / OpenCode 2.1.4 / Pi 1.4.0 / Claude Code 2.1.310, deepseek, moca at 250 steps): 11/12 for each zen agent, 8/12 for Claude Code, `filter-js` lost by all four. The round was repeated unchanged and held: moca and Pi
11/12 again, 45 of 48 cells identical, OpenCode 10/12, Claude Code 10/12. Details and the honest caveats are in [`docs/agents-bench-report.md`](docs/agents-bench-report.md). A four-agent in-container smoke (4/4 reward 1.0, every version confirmed in `result.json`) dates from the same day.
- Historical one-off reports keep their forensic detail: [2026-10-11](docs/bench-2026-10-11-moca-claude-code-pi.md) and [2026-10-16](docs/bench-2026-10-16-moca-claude-code-pi-opencode.md). Both are superseded by the tracking reports above.

## References

- Harbor docs — https://docs.harborframework.com
- Terminal-Bench — https://www.tbench.ai (leaderboard: https://www.tbench.ai/leaderboard/terminal-bench/2.0)
- Custom agents guide — https://docs.harborframework.com/agents/custom-agents
- Uploading to the Hub: `harbor upload results/jobs/<job>`. Harbor redacts agent-env values in stored configs (verified on 0.25.0: the entry is stored as the reference `${OPENCODE_API_KEY}`; 0.24.0 wrote `oc_s****ifJ`), and redaction can keep a short prefix/suffix — review the job directory before sharing, or pass secrets at launch time (`--launch --one-off-secret`) instead of by `--ae`.
