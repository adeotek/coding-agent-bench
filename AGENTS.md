# AGENTS.md — coding-agent-bench

A reproducible benchmark that runs four coding agents — **moca**, **OpenCode**, **Pi**, **Claude Code** — on identical [Terminal-Bench 2.0](https://www.tbench.ai/) tasks through [Harbor](https://github.com/harbor-framework/harbor), orchestrated by `make` targets. Small surface: two custom Harbor integrations + three scripts. Python is stdlib-only; bash has no dependencies beyond docker/uv.

## Ground truth (read before changing behavior)

- `README.md` — the user-facing walkthrough (setup, credentials, profiles, knobs, troubleshooting). Update it in the same commit as any user-visible change.
- **Harbor is external and version-pinned.** The installed package (`$(uv tool dir)/harbor/lib/python*/site-packages/harbor/`, version = `HARBOR_VERSION`) is the authoritative API reference for agent base classes, the JobConfig schema, and the CLI. Read the installed code (or `harbor run --help`, `harbor job schema`) — never guess an API from the web docs, which track `main`, not the pin.
- **Harbor is pinned to 0.25.0 and the pin is enforced.** `scripts/bench.sh run|dry-run` abort when
  the installed version differs (`HARBOR_ALLOW_VERSION_MISMATCH=1` is the deliberate override), and
  `make test` asserts that behaviour. Install with `./scripts/bench.sh setup --force`, which passes
  `--python $HARBOR_PYTHON`: a bare `uv tool install harbor` on a host with Python 3.15 resolves a
  3.15 tool env, fails to build `fastuuid`, and leaves **no harbor binary at all** — that is how
  0.25.0 landed mid-run on 2026-10-26. 0.25 also moved `ModelConnectionSpec` to
  `harbor.agents.agent_auth_resolution` and replaced `api_key_envs=` with
  `agent_provider_access=ProviderAccess(...)` + `api_key_destination_names`; `agents/moca.py`
  carries that shape.
- The agents under test are external too: pin releases (`MOCA_VERSION`, per-agent `kwargs.version`) — this repo never patches or forks an agent to make it look better.
- **moca's release line runs ahead of the last measured round.** v0.7.5–v0.7.12 are released; `MOCA_VERSION` is pinned to **v0.7.12** (2026-10-30), which raises the output ceiling on the retry after a truncated turn (`min(model limit, context.reserveTokens) × 2^attempt`, capped at the model's own limit — 16 384 by default while `deepseek-v4.1-flash` can emit 384 000) and allows up to three rescues per run, reset by any tool call, the v0.7.11 rescue having been too narrow: at k=10 on `regex-chess` the retry truncated again immediately in 8 of 10 trials. v0.7.11 (2026-10-28) was the narrower first cut — one retry at a reduced effort, no ceiling change — found by this bench's 21-cell screen (`regex-chess`, `adaptive-rejection-sampler` lost to 39k–61k-character thinking turns). The
  newest *measured* release is **v0.7.12**, and the measurement is a pre-registered k=10 on the cell it
  was built for: `regex-chess` **10/10** (`cab-subset-20261030-122349-959024`, $1.0703, 3 h 01 m) against
  **2/10** on both v0.7.10 and v0.7.11 (Fisher p = 0.0007), with truncations still occurring in 6/10 trials
  and **none** ending a run (11 rescues, 0 bound hits). The price is in the same row: 32 m and $0.107 per
  attempt against 5 m and $0.035. That supersedes the v0.7.11 reading — **18/23** on the 2026-10-28 sweep
  (`cab-subset-20261028-154055-3278028`), the same 18/23 as v0.7.10's sweep and 19/24 on 2026-10-26, one
  cell either way being this bench's own noise. The 23-cell sweep has NOT been re-run on v0.7.12, and the
  pre-registration (`docs/prereg-2026-10-30-truncation.md`) is the template for how a release gets measured
  here: metrics fixed before the run, reward explicitly declared undecidable at n=10.

The 12-task subset's **v0.7.10: 11/12** (2026-10-25, `…-014057-1313816`, and the hold-study repeat `…-100949-2263993`: 22/24 combined, identical cell pattern) is still the last subset round — it has not been re-run on v0.7.11 or v0.7.12. Every one of those rounds also moved the model or the step budget at least once, so they are baselines, not release credits. From v0.7.10 moca discovers each provider's model list at session start and validates the configured `model` against it (fail-open on discovery errors, but an unlisted id fails the session) — `make doctor` probes the same `/models` catalog for `ZEN_MODEL` and warns when the id is not listed; the hard stop is moca's own `Registry.Verify` at session start, not the preflight.

## Commands (verification ladder — cheapest first)

```bash
make help                    # list targets
make setup                   # uv tool install harbor==$HARBOR_VERSION + docker check
make test                    # harness unit tests (5 suites): moca run line, report parsers, pin guard
make doctor                  # docker, harbor, adapter import, credential presence
make audit                   # oracle+nop over docs/tb2-all.txt: no tokens, batches + image cleanup
make sharded PROFILE=full SHARDS=5   # one set as 5 sequential jobs; resumable, prunes images between
make doctor ARGS=--probe     # + one live request per agent (cents; needs .env)
make dry-run ARGS=smoke      # validate config + import path + kwargs + credentials — no pulls, no tokens
bash -n scripts/bench.sh && python3 -m py_compile scripts/render_config.py
PYTHONPATH=$PWD "$(uv tool dir)/harbor/bin/python" -c 'import agents.moca; print(agents.moca.Moca.name())'
make -n <target>             # show what a target would run, without running it
```

- Live steps — `probe`, `smoke`, `subset`, `full` — spend the user's API money and pull GB-sized images. Run them only when the user asks for a run; use `make dry-run` for everything else.
- Results land in `results/jobs/<job>/<trial>/`: `agent/` holds the agent logs (plus `moca-session.jsonl` for moca), and `result.json`'s `agent_result` carries tokens/cost. `make view` / `make net-view` browse them.

## Layout & contracts

- **`agents/moca.py`** — moca is not pre-integrated in Harbor (`BaseInstalledAgent`); passed as `import_path: agents.moca:Moca` (needs `PYTHONPATH` = repo root; `bench.sh` sets it). Contracts:
  - *install*: downloads `moca-<version>-linux-<arch>.tar.gz` + `checksums.txt` from the `adeotek/moca` GitHub release; sha256-verified. Keep the asset's original filename — `sha256sum -c` resolves names from *inside* the checksums file, not from the local path.
  - *run*: writes `~/.config/moca/config.jsonc` naming the model with the key as `env:OPENCODE_API_KEY` (indirection only — moca rejects literal keys; the name is also moca's own default for `opencode-go`, so the whole zen side of the bench reads one variable) and `context.maxSteps` (kwarg `max_steps`, default 250, moca's own default is 40); executes `moca --mode yolo -p <instruction>` — the mode comes from the `mode` kwarg, rendered from `MOCA_MODE` and defaulted to `yolo`, because v0.7.2 made `auto` moca's own default and the stance must be explicit in the job config (v0.4.0 replaced the `--yolo` flag with permission modes; `permission_flags()` picks the dialect from the pinned version, so v0.3.x pins still run — bisect-friendly); tees output to `$environment_logs_dir/moca.txt` and copies the session JSONL to `moca-session.jsonl` — with a **background mirror** (`run_command()`) refreshing that copy every 5 s while the run is in flight, because the final copy never executes when Harbor kills the agent phase (the 900 s timeout, a cancel) and the transcript is what carries the token/cost accounting.
  - *metrics*: `populate_context_post_run` sums `usage.{input,output,cacheRead,cacheWrite}` and `cost` from the session → `n_input_tokens` (incl. cache), `n_output_tokens`, `n_cache_tokens`, `cost_usd`. If moca's session schema changes, update this parser and re-verify `agent_result` in a smoke run.
  - *exit 3*: `NonZeroAgentExitCodeError` = moca's step-budget wrap-up (or stuck loop) — incomplete, but score the verifier reward anyway; completed-enough work can still pass.
- **`agents/opencode_v2.py`** — OpenCode v2 needs a custom integration because Harbor 0.25.0's built-in `opencode` agent still drives v1 (installs `opencode-ai`; hardcodes `--dangerously-skip-permissions` and a global `--model`). The subclass overrides only `install()` (npm `@opencode/cli`, explicit idempotent `postinstall.mjs` run — npm ≥ 12 blocks install scripts by default) and `run()` (`opencode run --standalone --format=json --thinking --auto --model=… --`), passing the version via `kwargs.version`. Everything else — JSON-event trajectory/metrics parsing, config/skills registration, credential plumbing via `OPENCODE_API_KEY` — is inherited and was verified against a real v2.0.30 run (v2's `step_finish.token`/`cost` shape is unchanged; keep it that way or fix the inherited parser's assumptions in a subclass override).
- **`scripts/render_config.py`** — single source of the effective JobConfig. Invariants: moca/OpenCode/Pi share `ZEN_MODEL`; `claude-code` uses `CLAUDE_MODEL` (it cannot use a zen key — intentional); dataset pinned to `terminal-bench` `2.0`; profiles `smoke | subset | full`; custom agents via `import_path` (moca, opencode v2), pre-integrated agents via `name`. Defaults: `opencode-go/deepseek-v4.1-flash`, `anthropic/claude-sonnet-5`, `MOCA_VERSION=v0.7.12`, `MOCA_MAX_STEPS=250`, `MOCA_MODE=yolo`, `OPENCODE_VERSION=2.1.4`, `PI_VERSION=1.4.0`, `CLAUDE_VERSION=2.1.310`, `N_TASKS=20`, `N_CONCURRENT=2`, `N_ATTEMPTS=3` for `subset`/`full` and 1 for `smoke`/`audit` (a per-cell verdict needs ≥3 attempts; a comparison run forced to 1 prints a warning). Knobs are env vars — add README's table row when adding one.
- **`scripts/bench.sh`** — orchestration layer: loads `.env`, assembles the `--ae` arguments, exports `PYTHONPATH`, renders, runs Harbor. `run` renders to a per-run config file (`results/effective-<profile>-<timestamp>-<pid>.json`, with the canonical `effective-<profile>.json` refreshed for inspection) and passes a matching unique `--job-name` (`cab-<profile>-<timestamp>-<pid>`) — Harbor names job directories by second, so concurrent legs would otherwise collide; `dry-run`/`render` keep the canonical path. Keep `make` targets thin wrappers around it; logic belongs here.
- **`scripts/runlist.sh` + `docs/tb2-measurable.txt` / `docs/tb2-watch.txt`** — the run lists are
  **derived** from the audit job store (never hand-edited): measurable = oracle-green cells here,
  watch = the rest with their class. `render_config.py` drops watch-listed cells from non-audit
  profiles, by name and on stderr, unless `ALLOW_DEFECTIVE=1`; the `audit` profile is exempt
  because re-finding them is its job. A cell earns its way back only by its own oracle passing —
  `scripts/audit-watch.sh` re-audits the broken ones (zero tokens; host-limited ones are skipped
  by default because re-running them on the same host just reproduces the failure, `WATCH_ALL=1`
  forces it) and refreshes both lists.
- **`tasks/`** — the cells this bench owns: `repairs/` (upstream cells whose verifier was broken, fixed),
  `parked/` (a repair that could not be finished honestly), `authored/` (tasks written here for the failure
  modes the measured rounds found). Run them with `LOCAL_TASKS=<dir>`; `render_config.py` turns that into a
  `dataset.path` instead of a registry name, keeps `task_names` filtering, accepts a single task dir as a
  one-task shorthand, and exempts the cells from the watch-list filter. **Their results are local-only** —
  never quote them as terminal-bench numbers, and never mix them into a sweep whose other columns came from
  the registry. A repair is done only when **oracle passes and nop fails** on the local copy
  (`make local-audit`, zero model tokens); the defect, the evidence and the audit live in
  `docs/task-repairs.json`. A test may be strict, but it must test the task, not the reference solution's
  private choices, the verifier's own network access, or an artifact left by the agent's own smoke test.
- **`scripts/cell_stability.py`** — derives `docs/cell-stability.json` + `docs/tb2-ranking.txt` from the
  job store: per (cell, agent) k/n, Wilson interval and class (`passes`/`fails`/`flaky`/`insufficient`
  under 3 attempts), plus the cells that can actually rank agents (≥2 agents measured ≥3 times, rates
  ≥ 0.33 apart, `docs/task-side.json` cells excluded, **and jobs whose dataset is a local `path` skipped** —
  a repaired or authored cell must never enter the terminal-bench registry, even when its name also exists
  upstream; the skipped job names are recorded in `generated_from.local_jobs_skipped`), Harbor's
  `nop`/`oracle` calibration columns
  excluded, only each agent's newest release folded — a rate mixing v0.7.10–v0.7.12 answers nothing).
  Never hand-edit either file; regenerate.
- **`scripts/determinism_probe.py`** — asks the endpoint whether the sampling noise is removable: N
  identical requests with `temperature: 0` + fixed `seed` + fixed `x-opencode-session`, the same without
  sampling parameters, and the pinned request on a fresh session per call. The go endpoint rejects a
  request without a session header (`MissingSessionID`) and Cloudflare rejects urllib's default UA
  (`error code: 1010`), so both headers are mandatory.
- **`scripts/probe-auth.sh`** — local credential probes with scratch state dirs. Secrets travel only via inherited environment (never argv), are never printed, and each probe mirrors the container's credential flow (not its binary versions).
- **`scripts/bench_report.py`** — re-derives every table in the two reports from `results/jobs/`
  (`matrix` prints `k/n rate (95% Wilson interval)` and **refuses** a job whose cells were attempted once
  — exit 2, `--allow-n1` for forensics; a letter from a single draw is how four cell-level claims in this
  repo's history got written). (`runs | summary <job> | matrix <job>… | steps <job>… | credit <job>… | export <job>… | report <job>… | compare <job>… | diff <job> <task> | json <job>…`). `steps` reads the agent transcript rather than `result.json` — moca's `moca-session.jsonl` (one record per assistant turn, own `usage`) and the other agents' ATIF `trajectory.json` (one `source: agent` step per turn) — and reports turns, tool calls, tokens/turn and proximity to the step cap; its moca token total must equal `result.json`'s `n_input_tokens` (verified: 8.54 M on `…100949-2263993`). The job store is ground truth; the report prose is not. Reading `verifier_result.reward` instead of `verifier_result.rewards.reward` yields `None` for every trial — the script exists partly to keep that mistake out of the reports.
- **`docs/tb2-subset-24.txt`** — the comparison set for post-screening rounds: the fixed 12 (byte-identical
  prefix, so `grep -v '^#' … | head -12` reproduces the old set) plus 12 cells chosen from the screening
  sweep because moca fails them or only passes them by grinding. Expected moca score ~18–20/24; the
  12-task set is saturated and cannot show a release improving anything.
- **`docs/tb2-screen.txt` + `docs/tb2-screen-batch-1.txt`** — the 77 terminal-bench 2.0 tasks this bench has
  never run, ordered cheap-first (tier 1 = filter-js sibling + repo forensics), sliced 10 at a time by
  `make screen BATCH=N` (moca only, 1 attempt). This is the failure corpus: the 12-task subset is
  saturated, so hardening comes from cells moca drops here — read it with `bench_report.py steps`.
- **`docs/moca-bench-report.md` + `docs/agents-bench-report.md`** — the two tracking reports. **Update both in the same commit as any run**: add the row/column, re-derive the matrix, write the per-cell diagnosis, and refresh the moca report's closing summary (latest release vs all previous, open issues, actions for the next release). Keep every earlier run in place — the reports are the run history, not a snapshot.
- **`scripts/audit.sh` + `render_config.py audit` profile** — Harbor's `oracle` (must pass) and
  `nop` (must fail) over `docs/tb2-all.txt`. `audit.sh` batches the run and `docker rmi`s each
  batch's images except the 24-task comparison set's, because 89 images do not fit in this
  host's free space. `bench_report.py audit` classifies: healthy / broken-task (oracle fails) /
  vacuous (nop passes) / both-broken / no-verdict / unknown. **`no-verdict` is never folded into
  a side** — an infrastructure failure is not a task-quality verdict. A task-side entry in
  `docs/task-side.json` should cite an audit row or a transcript.
- **Sharding (`SHARD=k/n`, `scripts/sharded_run.sh`)** — a job may be one slice of a set,
  because 89 images ≈ 145 GB uncompressed and Harbor holds every image for a job's
  lifetime. Contracts: the slice is a contiguous ceil-sized block (disjoint, ordered,
  union = parent list); the manifest records `shard.parent_task_list_sha256`, and
  `comparable()` compares *that* rather than the slice's own fingerprint; a stitched
  `report`/`compare` prints its coverage (`71/89, 18 uncovered`) and warns when shards
  come from different parents. **A partial set must never read as a whole one.** `SHARD`
  requires an explicit list — slicing `n_tasks` would guess what Harbor picks.
- **`scripts/manifest.py`** — `bench.sh run` calls `start` before launching Harbor and `finish`
  after it, so every job directory carries `manifest.json`: harbor version + interpreter, repo
  commit/branch/dirty, dataset + task-list fingerprint, agents with model ids and versions, the
  knob values set in the launching shell, trial counts read back from `result.json`, and image
  digests (best-effort — pruned images are `null`, never an error). `compare` calls
  `comparable()` and **warns** when two jobs differ in toolchain, knobs or task list, and when a
  job predates manifests. Jobs from before 2026-10-26 have no manifest; the warning is the
  honest record of that.
- **`docs/task-side.json`** — the registry of cells with a *demonstrated* verifier defect (not
  "hard", not "flaky"). `report`/`export` exclude them from scores and print them under
  "Excluded", because the history must stay comparable; `--include-task-side` puts them back.
  Adding an entry requires reading the verifier **and** the transcripts, and citing both in the
  `evidence` field.
- **Partial credit** — `credit` parses `verifier/ctrf.json` (`results.summary`, `results.tests`)
  and scores passed/total excluding `skipped`. Secondary metric only: a task is solved or not,
  and it resolves ~3.4× finer than binary on this set (82 tests vs 24 cells).
- **`Makefile`** — thin wrappers; each target documented with a `## ` comment (that feeds `make help`).
  `make local-audit` runs the oracle/nop audit of `tasks/` through `scripts/audit-local.sh` (zero tokens).
- **`results/`** — gitignored output. Treat transcripts and logs as potentially sensitive; never commit.

## Credentials (how each agent receives its key)

| Agent | In-container variable | Delivery |
|---|---|---|
| moca | `OPENCODE_API_KEY` (config references it via `env:`; also moca's own default for `opencode-go`) | `.env` → `--ae` (by `bench.sh`) |
| OpenCode, Pi | `OPENCODE_API_KEY` | `.env` → `--ae` (by `bench.sh`) |
| Claude Code | `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` | auto-forwarded by Harbor from the process environment |

Harbor's provider registry does not know the `opencode-go` provider, which is exactly why `bench.sh` passes the keys explicitly with `--ae`. Stored job configs mask env values (`oc_s****ifJ`) but keep a prefix/suffix — review `results/jobs/<job>/` before `harbor upload`.

## Editing rules

- **`main` is PR-only.** Never commit or push to `main` directly — cut a branch, push it, open a pull request (GitHub does not enforce this on this repo; the rule is a convention, so it has to be remembered). Don't merge the PR without the user's explicit approval.
- Keep the comparison fair, or make the change visible: same model for the three zen agents, same task set, same Docker sandbox, permissive modes everywhere (`moca --mode yolo`, OpenCode `--auto`, Claude `bypassPermissions`). Any changed pin or knob goes in the commit message and README.
- Non-interactive shells: pass `-y` to `harbor run` — a confirmation prompt otherwise hangs the job.
- Ports: `harbor view` `--port` takes a single port or a range (default `8080-8089`, first free wins); a single occupied port fails with "No available port found". `make net-view` binds `0.0.0.0` — **the viewer is unauthenticated** and has state-changing endpoints gated only by browser-origin checks: keep it LAN-only, open the firewall deliberately.
- Docker disk: Terminal-Bench images are GB-sized pulls; `make doctor` reports free space, `make prune` reclaims.
- Version drift: OpenCode/Pi/Claude Code install their `@latest` by default; pin with `"kwargs": {"version": "<v>"}` in `render_config.py` when a comparison must be reproducible.
- This repo is public: no personal hostnames, IPs, or infra paths in tracked files; no secrets ever (`.env` is gitignored — scan before pushing if in doubt).
