#!/usr/bin/env bash
# coding-agent-bench — run Terminal-Bench 2.0 (via Harbor) across moca,
# OpenCode, Pi, and Claude Code on identical tasks.
#
#   ./scripts/bench.sh setup              install Harbor (pinned) + check docker
#   ./scripts/bench.sh doctor [--probe]   check binaries, adapter, credentials
#   ./scripts/bench.sh probe              live 1-token credential probes
#   ./scripts/bench.sh dry-run [profile]  validate the rendered job config
#   ./scripts/bench.sh run <profile> [args...]   smoke | subset | full
#   ./scripts/bench.sh render [profile]   write results/effective-<p>.json
#   ./scripts/bench.sh view [args...]     browse job results (args pass to harbor view)
#   ./scripts/bench.sh prune              reclaim docker disk
#
# See README.md for the full walkthrough.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# .env carries credentials + run knobs; it is gitignored and never committed.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

PYTHON="${PYTHON:-python3}"
HARBOR="${HARBOR:-harbor}"
HARBOR_VERSION="${HARBOR_VERSION:-0.24.0}"
JOBS_DIR="${JOBS_DIR:-results/jobs}"
HBPY="$(uv tool dir 2>/dev/null || true)/harbor/bin/python"

die() { echo "error: $*" >&2; exit 1; }

need_harbor() {
  command -v "$HARBOR" >/dev/null 2>&1 ||
    die "harbor not found — run: ./scripts/bench.sh setup"
}

render() { # profile [out-path] -> prints config path
  local profile="$1" out="${2:-}"
  if [ -n "$out" ]; then
    "$PYTHON" scripts/render_config.py "$profile" -o "$out"
  else
    "$PYTHON" scripts/render_config.py "$profile"
  fi
}

# Agent-phase env for the provider-dependent agents. The values are expanded
# here from the shell environment; the .env file itself is never handed to
# Harbor. (Note: expanded values appear transiently in this process's argv.)
AE_ARGS=()
agent_env_args() {
  AE_ARGS=()
  if [ -n "${OPENCODE_GO_KEY:-}" ]; then
    AE_ARGS+=(--ae "OPENCODE_API_KEY=$OPENCODE_GO_KEY")
    AE_ARGS+=(--ae "OPENCODE_GO_KEY=$OPENCODE_GO_KEY")
  fi
}

cmd_setup() {
  command -v uv >/dev/null 2>&1 ||
    die "uv is required — https://docs.astral.sh/uv/"
  if command -v harbor >/dev/null 2>&1; then
    echo "harbor $(harbor --version) already installed"
  else
    uv tool install "harbor==$HARBOR_VERSION"
  fi
  docker version --format 'docker server {{.Server.Version}}' >/dev/null 2>&1 ||
    die "docker daemon not reachable"
  echo "docker OK — next: ./scripts/bench.sh doctor"
}

cmd_doctor() {
  local probe=0
  [ "${1:-}" = "--probe" ] && probe=1

  echo "== docker"
  if docker version --format 'server {{.Server.Version}}' >/dev/null 2>&1; then
    docker version --format 'server {{.Server.Version}}'
  else
    echo "NOT reachable — is the daemon running? is \$USER in the docker group?"
  fi

  echo
  echo "== harbor"
  if command -v harbor >/dev/null 2>&1; then
    echo "harbor $(harbor --version) (configured pin: $HARBOR_VERSION)"
  else
    echo "NOT installed — run: ./scripts/bench.sh setup"
  fi

  echo
  echo "== disk (docker root)"
  local root avail
  root="$(docker info -f '{{.DockerRootDir}}' 2>/dev/null || echo /var/lib/docker)"
  avail="$(df -BG --output=avail "$root" 2>/dev/null | tail -1 | tr -d ' G' || true)"
  echo "${avail:-?}G available on $root — Terminal-Bench image pulls are GBs; prune between runs"

  echo
  echo "== moca adapter (agents/moca.py)"
  if [ -x "$HBPY" ]; then
    PYTHONPATH="$REPO" "$HBPY" -c \
      'import agents.moca as m; print("import OK:", m.Moca.name(), "| default pin:", m._DEFAULT_VERSION)'
  else
    echo "skip: $HBPY not found (install harbor first)"
  fi

  echo
  echo "== credentials (values not shown)"
  for v in OPENCODE_GO_KEY ANTHROPIC_API_KEY CLAUDE_CODE_OAUTH_TOKEN; do
    if [ -n "${!v:-}" ]; then echo "  $v: set"; else echo "  $v: unset"; fi
  done

  if [ "$probe" = 1 ]; then
    echo
    echo "== live probes (one tiny request per agent, local binaries)"
    bash scripts/probe-auth.sh
  fi
}

cmd_dry_run() { # [profile]
  need_harbor
  agent_env_args
  local profile="${1:-subset}" cfg
  cfg="$(render "$profile")"
  echo "== effective config: $cfg"
  PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" \
    "$HARBOR" run --config "$cfg" --dry-run "${AE_ARGS[@]}"
}

cmd_run() { # profile [extra harbor args...]
  need_harbor
  agent_env_args
  local profile="${1:-subset}"
  shift || true
  # Render to a per-run file: two concurrent runs sharing results/effective-<p>.json
  # could otherwise pick up each other's config between render and exec (a silent
  # model swap). The canonical name is refreshed for inspection, and the job
  # directory keeps the authoritative copy of what actually ran.
  local run_id="$(date +%Y%m%d-%H%M%S)-$$"
  local run_cfg="results/effective-$profile-$run_id.json" cfg
  cfg="$(render "$profile" "$run_cfg")"
  cp "$cfg" "results/effective-$profile.json"
  echo "== effective config: $cfg"
  # A unique job name too: Harbor names the job directory by second
  # (cab-<profile>-<YYYYmmdd-HHMMSS>), so two legs launched in the same second
  # collide ("Job directory … already exists and cannot be resumed with a
  # different config") and one dies instantly. The pid makes it unique.
  PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" \
    "$HARBOR" run --config "$cfg" --job-name "cab-$profile-$run_id" "${AE_ARGS[@]}" "$@"
}

cmd_view() { # [extra harbor view args...]
  need_harbor
  "$HARBOR" view "$JOBS_DIR" "$@"
}

cmd_prune() {
  docker image prune -f
  docker system prune -f
}

case "${1:-help}" in
  setup) cmd_setup ;;
  doctor) shift || true; cmd_doctor "${1:-}" ;;
  probe) bash scripts/probe-auth.sh ;;
  dry-run | dryrun) shift || true; cmd_dry_run "${1:-subset}" ;;
  run) shift || true; cmd_run "$@" ;;
  render) shift || true; render "${1:-subset}" ;;
  view) shift || true; cmd_view "$@" ;;
  prune) cmd_prune ;;
  help | -h | --help) sed -n '2,16p' "$0" ;;
  *) die "unknown command '${1}' — see ./scripts/bench.sh help" ;;
esac
