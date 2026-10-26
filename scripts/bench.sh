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
# Harbor is pinned: the adapters and the JobConfig renderer are written against this
# exact release. Upgrades are deliberate (bump here + README + AGENTS.md, re-run the
# ladder), never incidental.
HARBOR_VERSION="${HARBOR_VERSION:-0.25.0}"
# uv picks the newest interpreter by default, and a bare `uv tool install harbor` on a
# host with Python 3.15 fails to build fastuuid and leaves NO harbor binary behind.
# 3.14 is the highest release with full wheel coverage for Harbor's dependency tree
# (and matches the host's own python3); 3.13 remains a working fallback.
HARBOR_PYTHON="${HARBOR_PYTHON:-3.14}"
JOBS_DIR="${JOBS_DIR:-results/jobs}"
HBPY="$(uv tool dir 2>/dev/null || true)/harbor/bin/python"

die() { echo "error: $*" >&2; exit 1; }

need_harbor() {
  command -v "$HARBOR" >/dev/null 2>&1 ||
    die "harbor not found — run: ./scripts/bench.sh setup"
}

harbor_version() {
  "$HARBOR" --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1
}

# Version drift has already poisoned one run (0.24 -> 0.25 landed mid-job) and a
# mismatch is invisible until something imports a moved module. Hard-fail instead.
require_harbor_pin() {
  local have; have="$(harbor_version)"
  [ -n "$have" ] || die "could not read the harbor version — run: ./scripts/bench.sh setup"
  if [ "$have" != "$HARBOR_VERSION" ]; then
    if [ "${HARBOR_ALLOW_VERSION_MISMATCH:-0}" = "1" ]; then
      echo "WARN: harbor $have != pin $HARBOR_VERSION (allowed by HARBOR_ALLOW_VERSION_MISMATCH=1)" >&2
      return 0
    fi
    die "harbor $have is installed but the pin is $HARBOR_VERSION — fix with: ./scripts/bench.sh setup --force
     (or set HARBOR_ALLOW_VERSION_MISMATCH=1 for a one-off)"
  fi
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
#
# One variable names the zen key everywhere: OPENCODE_API_KEY — moca's own
# built-in default for the `opencode-go` provider, and the name OpenCode and Pi
# read. OPENCODE_GO_KEY is the pre-2026-10 name; it is still accepted (with a
# warning) so an older .env keeps working, but nothing new should set it.
AE_ARGS=()
_ZEN_KEY_WARNED=""
zen_key() {
  local key="${OPENCODE_API_KEY:-}"
  if [ -z "$key" ] && [ -n "${OPENCODE_GO_KEY:-}" ]; then
    key="$OPENCODE_GO_KEY"
    if [ -z "$_ZEN_KEY_WARNED" ]; then
      echo "warning: OPENCODE_GO_KEY is deprecated — rename it to OPENCODE_API_KEY in .env" >&2
      _ZEN_KEY_WARNED=1
    fi
  fi
  printf '%s' "$key"
}

agent_env_args() {
  AE_ARGS=()
  local key
  key="$(zen_key)"
  if [ -n "$key" ]; then
    AE_ARGS+=(--ae "OPENCODE_API_KEY=$key")
  fi
}

# moca >= v0.7.10 discovers each provider's model list and validates the
# configured `model` against it (fail-open on discovery errors, but a resolved
# model that the catalog does not list fails the session). Probe the catalog
# the same way so a retired or renamed model id is caught before a sweep.
zen_models_url() { # provider -> public /models URL (zen gateways only)
  case "$1" in
    opencode-go) echo "https://opencode.ai/zen/go/v1/models" ;;
    opencode)    echo "https://opencode.ai/zen/v1/models" ;;
    *) return 1 ;;
  esac
}

check_model_id() {
  local model="${ZEN_MODEL:-opencode-go/deepseek-v4.1-flash}" provider id url key body
  provider="${model%%/*}"
  id="${model#*/}"
  key="$(zen_key)"
  if ! url="$(zen_models_url "$provider")"; then
    echo "skip: $provider is not a zen gateway (no public /models probe)"
    return
  fi
  if [ -z "$key" ]; then
    echo "skip: no zen key set"
    return
  fi
  # The key travels in a curl config read from stdin, never in argv.
  local hdr="Authorization: Bearer ${key}"
  if ! body="$(printf 'header = "%s"\n' "$hdr" |
      curl -fsS -m 15 --config - "$url" 2>/dev/null)"; then
    echo "WARN: could not read $url (network or auth) — model id unverified"
    return
  fi
  if printf '%s' "$body" | "$PYTHON" -c '
import json, sys
ids = [m.get("id") for m in json.load(sys.stdin).get("data", [])]
sys.exit(0 if sys.argv[1] in ids else 1)
' "$id"; then
    echo "OK: $model is listed by $provider ($url)"
  else
    echo "WARN: $id is not listed by $provider — moca >= v0.7.10 validates the"
    echo "      model against the discovered catalog and refuses to start (exit 2);"
    echo "      a released pin that lists it is fine only if discovery fails open."
  fi
}

cmd_setup() {
  command -v uv >/dev/null 2>&1 ||
    die "uv is required — https://docs.astral.sh/uv/"
  local want_force=0
  [ "${1:-}" = "--force" ] && want_force=1
  local have; have="$(command -v harbor >/dev/null 2>&1 && harbor_version)"
  if [ "$have" = "$HARBOR_VERSION" ] && [ "$want_force" = "0" ]; then
    echo "harbor $have already installed (pin)"
  else
    [ -n "$have" ] && echo "replacing harbor ${have:-none} with the pin $HARBOR_VERSION"
    uv tool install --force --python "$HARBOR_PYTHON" "harbor==$HARBOR_VERSION" ||
      die "harbor install failed — is python $HARBOR_PYTHON available (uv python list)?"
    need_harbor
    require_harbor_pin
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
    local have; have="$(harbor_version)"
    if [ "$have" = "$HARBOR_VERSION" ]; then
      echo "harbor $have (pin OK)"
    else
      echo "harbor ${have:-unknown} MISMATCH — pin is $HARBOR_VERSION; run ./scripts/bench.sh setup --force"
    fi
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
      'import agents.moca as m; print("import OK:", m.Moca.name(), "| default pin:", m._DEFAULT_VERSION, "| key env:", m._API_KEY_ENV)'
  else
    echo "skip: $HBPY not found (install harbor first)"
  fi

  echo
  echo "== credentials (values not shown)"
  for v in OPENCODE_API_KEY OPENCODE_GO_KEY ANTHROPIC_API_KEY CLAUDE_CODE_OAUTH_TOKEN; do
    if [ -n "${!v:-}" ]; then echo "  $v: set"; else echo "  $v: unset"; fi
  done
  if [ -n "${OPENCODE_GO_KEY:-}" ] && [ -z "${OPENCODE_API_KEY:-}" ]; then
    echo "  note: OPENCODE_GO_KEY is the deprecated name — bench.sh still forwards it"
  fi

  echo
  echo "== model id (provider catalog)"
  check_model_id

  if [ "$probe" = 1 ]; then
    echo
    echo "== live probes (one tiny request per agent, local binaries)"
    bash scripts/probe-auth.sh
  fi
}

cmd_dry_run() { # [profile]
  need_harbor
  require_harbor_pin
  agent_env_args
  local profile="${1:-subset}" cfg
  cfg="$(render "$profile")"
  echo "== effective config: $cfg"
  PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" \
    "$HARBOR" run --config "$cfg" --dry-run "${AE_ARGS[@]}"
}

cmd_run() { # profile [extra harbor args...]
  need_harbor
  require_harbor_pin
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
  # Manifest: the toolchain, the knob values and the task-list fingerprint, written
  # BEFORE harbor starts so it survives a crash, then finished into the job dir.
  local job_name="cab-$profile-$run_id"
  local manifest="results/manifests/$job_name.json"
  local hp; hp="$("$(uv tool dir)/harbor/bin/python" -V 2>/dev/null | awk '{print $2}')"
  python3 "$REPO/scripts/manifest.py" start \
    --config "$cfg" --job-name "$job_name" --out "$manifest" \
    --harbor-version "$(harbor_version)" --harbor-python "${hp:-unknown}" \
    --knob "HARBOR_VERSION=$HARBOR_VERSION" --knob "HARBOR_PYTHON=$HARBOR_PYTHON" \
    --knob "MOCA_VERSION=${MOCA_VERSION:-}" --knob "MOCA_MAX_STEPS=${MOCA_MAX_STEPS:-}" \
    --knob "MOCA_MODE=${MOCA_MODE:-}" --knob "OPENCODE_VERSION=${OPENCODE_VERSION:-}" \
    --knob "PI_VERSION=${PI_VERSION:-}" --knob "CLAUDE_VERSION=${CLAUDE_VERSION:-}" \
    --knob "ZEN_MODEL=${ZEN_MODEL:-}" --knob "CLAUDE_MODEL=${CLAUDE_MODEL:-}" \
    --knob "N_ATTEMPTS=${N_ATTEMPTS:-}" --knob "N_CONCURRENT=${N_CONCURRENT:-}" \
    --knob "AGENTS=${AGENTS:-all}" --knob "TASK_NAMES=${TASK_NAMES:-}" \
    || echo "WARN: could not write the run manifest (the run continues)" >&2

  set +e
  PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" \
    "$HARBOR" run --config "$cfg" --job-name "$job_name" "${AE_ARGS[@]}" "$@"
  local rc=$?
  set -e
  python3 "$REPO/scripts/manifest.py" finish \
    --manifest "$manifest" --job-dir "results/jobs/$job_name" --exit-code "$rc" \
    || echo "WARN: could not finish the run manifest" >&2
  return "$rc"
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
  setup) shift; cmd_setup "$@" ;;
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
