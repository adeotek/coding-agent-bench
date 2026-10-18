# AGENTS.md — coding-agent-bench

A reproducible benchmark that runs four coding agents — **moca**, **OpenCode**, **Pi**, **Claude Code** — on identical [Terminal-Bench 2.0](https://www.tbench.ai/) tasks through [Harbor](https://github.com/harbor-framework/harbor), orchestrated by `make` targets. Small surface: two custom Harbor integrations + three scripts. Python is stdlib-only; bash has no dependencies beyond docker/uv.

## Ground truth (read before changing behavior)

- `README.md` — the user-facing walkthrough (setup, credentials, profiles, knobs, troubleshooting). Update it in the same commit as any user-visible change.
- **Harbor is external and version-pinned.** The installed package (`$(uv tool dir)/harbor/lib/python*/site-packages/harbor/`, version = `HARBOR_VERSION`) is the authoritative API reference for agent base classes, the JobConfig schema, and the CLI. Read the installed code (or `harbor run --help`, `harbor job schema`) — never guess an API from the web docs, which track `main`, not the pin.
- The agents under test are external too: pin releases (`MOCA_VERSION`, per-agent `kwargs.version`) — this repo never patches or forks an agent to make it look better.

## Commands (verification ladder — cheapest first)

```bash
make help                    # list targets
make setup                   # uv tool install harbor==$HARBOR_VERSION + docker check
make test                    # harness unit test: the moca run line + session mirror
make doctor                  # docker, harbor, adapter import, credential presence
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
  - *run*: writes `~/.config/moca/config.jsonc` naming the model with the key as `env:OPENCODE_GO_KEY` (indirection only — moca rejects literal keys) and `context.maxSteps` (kwarg `max_steps`, default 100, moca's own default is 40); executes `moca --mode yolo -p <instruction>` (v0.4.0 replaced the `--yolo` flag with permission modes; `permission_flags()` picks the dialect from the pinned version, so v0.3.x pins still run — bisect-friendly); tees output to `$environment_logs_dir/moca.txt` and copies the session JSONL to `moca-session.jsonl` — with a **background mirror** (`run_command()`) refreshing that copy every 5 s while the run is in flight, because the final copy never executes when Harbor kills the agent phase (the 900 s timeout, a cancel) and the transcript is what carries the token/cost accounting.
  - *metrics*: `populate_context_post_run` sums `usage.{input,output,cacheRead,cacheWrite}` and `cost` from the session → `n_input_tokens` (incl. cache), `n_output_tokens`, `n_cache_tokens`, `cost_usd`. If moca's session schema changes, update this parser and re-verify `agent_result` in a smoke run.
  - *exit 3*: `NonZeroAgentExitCodeError` = moca's step-budget wrap-up (or stuck loop) — incomplete, but score the verifier reward anyway; completed-enough work can still pass.
- **`agents/opencode_v2.py`** — OpenCode v2 needs a custom integration because Harbor 0.24.0's built-in `opencode` agent drives v1 (installs `opencode-ai`; hardcodes `--dangerously-skip-permissions` and a global `--model`). The subclass overrides only `install()` (npm `@opencode/cli`, explicit idempotent `postinstall.mjs` run — npm ≥ 12 blocks install scripts by default) and `run()` (`opencode run --standalone --format=json --thinking --auto --model=… --`), passing the version via `kwargs.version`. Everything else — JSON-event trajectory/metrics parsing, config/skills registration, credential plumbing via `OPENCODE_API_KEY` — is inherited and was verified against a real v2.0.30 run (v2's `step_finish.token`/`cost` shape is unchanged; keep it that way or fix the inherited parser's assumptions in a subclass override).
- **`scripts/render_config.py`** — single source of the effective JobConfig. Invariants: moca/OpenCode/Pi share `ZEN_MODEL`; `claude-code` uses `CLAUDE_MODEL` (it cannot use a zen key — intentional); dataset pinned to `terminal-bench` `2.0`; profiles `smoke | subset | full`; custom agents via `import_path` (moca, opencode v2), pre-integrated agents via `name`. Defaults: `opencode-go/glm-5.3-flash`, `anthropic/claude-sonnet-5`, `MOCA_VERSION=v0.6.4`, `MOCA_MAX_STEPS=100`, `OPENCODE_VERSION=2.0.30`, `PI_VERSION=1.3.0`, `CLAUDE_VERSION=2.1.301`, `N_TASKS=20`, `N_CONCURRENT=2`. Knobs are env vars — add README's table row when adding one.
- **`scripts/bench.sh`** — orchestration layer: loads `.env`, assembles the `--ae` arguments, exports `PYTHONPATH`, renders, runs Harbor. `run` renders to a per-run config file (`results/effective-<profile>-<timestamp>-<pid>.json`, with the canonical `effective-<profile>.json` refreshed for inspection) so concurrent runs cannot swap configs; `dry-run`/`render` keep the canonical path. Keep `make` targets thin wrappers around it; logic belongs here.
- **`scripts/probe-auth.sh`** — local credential probes with scratch state dirs. Secrets travel only via inherited environment (never argv), are never printed, and each probe mirrors the container's credential flow (not its binary versions).
- **`Makefile`** — thin wrappers; each target documented with a `## ` comment (that feeds `make help`).
- **`results/`** — gitignored output. Treat transcripts and logs as potentially sensitive; never commit.

## Credentials (how each agent receives its key)

| Agent | In-container variable | Delivery |
|---|---|---|
| moca | `OPENCODE_GO_KEY` (config references it via `env:`) | `.env` → `--ae` (by `bench.sh`) |
| OpenCode, Pi | `OPENCODE_API_KEY` | `.env` → `--ae` (by `bench.sh`) |
| Claude Code | `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` | auto-forwarded by Harbor from the process environment |

Harbor's provider registry does not know the `opencode-go` provider, which is exactly why `bench.sh` passes the keys explicitly with `--ae`. Stored job configs mask env values (`oc_s****ifJ`) but keep a prefix/suffix — review `results/jobs/<job>/` before `harbor upload`.

## Editing rules

- Don't commit or push without the user's explicit approval.
- Keep the comparison fair, or make the change visible: same model for the three zen agents, same task set, same Docker sandbox, permissive modes everywhere (`moca --yolo`, OpenCode `--dangerously-skip-permissions`, Claude `bypassPermissions`). Any changed pin or knob goes in the commit message and README.
- Non-interactive shells: pass `-y` to `harbor run` — a confirmation prompt otherwise hangs the job.
- Ports: `harbor view` `--port` takes a single port or a range (default `8080-8089`, first free wins); a single occupied port fails with "No available port found". `make net-view` binds `0.0.0.0` — **the viewer is unauthenticated** and has state-changing endpoints gated only by browser-origin checks: keep it LAN-only, open the firewall deliberately.
- Docker disk: Terminal-Bench images are GB-sized pulls; `make doctor` reports free space, `make prune` reclaims.
- Version drift: OpenCode/Pi/Claude Code install their `@latest` by default; pin with `"kwargs": {"version": "<v>"}` in `render_config.py` when a comparison must be reproducible.
- This repo is public: no personal hostnames, IPs, or infra paths in tracked files; no secrets ever (`.env` is gitignored — scan before pushing if in doubt).
