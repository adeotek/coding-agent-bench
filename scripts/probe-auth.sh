#!/usr/bin/env bash
# Live credential probes — one tiny real request per agent, emulating the
# container environment (scratch state dirs, env-var credentials only).
#
# This validates that the API key flows the way coding-agent-bench passes it:
#   OPENCODE_API_KEY  for moca, OpenCode, Pi (opencode-go)
#   ANTHROPIC_API_KEY | CLAUDE_CODE_OAUTH_TOKEN  for Claude Code (auto-forwarded)
#
# Binaries are the LOCAL ones (override with MOCA_BIN / OPENCODE_BIN / PI_BIN /
# CLAUDE_BIN). This checks credential plumbing, not container versions.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "$REPO/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$REPO/.env"
  set +a
fi

ZEN_MODEL="${ZEN_MODEL:-opencode-go/deepseek-v4.1-flash}"
PROMPT="Reply with exactly: ok"
MOCA_BIN="${MOCA_BIN:-$HOME/projects/moca/bin/moca}"
OPENCODE_BIN="${OPENCODE_BIN:-$HOME/.opencode/bin/opencode}"
PI_BIN="${PI_BIN:-$(command -v pi || true)}"
CLAUDE_BIN="${CLAUDE_BIN:-$(command -v claude || true)}"

if [ -z "${OPENCODE_API_KEY:-}" ]; then
  echo "error: OPENCODE_API_KEY is not set (put it in $REPO/.env)" >&2
  exit 1
fi
# Already exported by the `set -a` .env source above; the key reaches every
# probe through the environment, never argv.

WORK="$(mktemp -d "${TMPDIR:-/tmp}/cab-probe.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

pass=0
fail=0
skip=0

probe() { # name -- command...
  local name="$1"
  shift 2
  echo "--- probe: $name"
  local out rc
  out="$(timeout 180 "$@" 2>&1)"
  rc=$?
  if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -qiE '(^|[^a-z])ok([^a-z]|$)'; then
    echo "PASS: $name"
    pass=$((pass + 1))
  else
    echo "FAIL: $name (exit $rc)"
    printf '%s\n' "$out" | tail -n 12 | sed 's/^/    /'
    fail=$((fail + 1))
  fi
}

# --- moca -------------------------------------------------------------------
mkdir -p "$WORK/moca/cfg" "$WORK/moca/data" "$WORK/moca/state"
printf '{\n  "model": "%s",\n  "providers": { "opencode-go": { "apiKey": "env:OPENCODE_API_KEY" } }\n}\n' \
  "$ZEN_MODEL" >"$WORK/moca/cfg/config.jsonc"
if [ -x "$MOCA_BIN" ]; then
  probe moca -- env \
    XDG_CONFIG_HOME="$WORK/moca/cfg" \
    XDG_DATA_HOME="$WORK/moca/data" \
    XDG_STATE_HOME="$WORK/moca/state" \
    "$MOCA_BIN" --config "$WORK/moca/cfg/config.jsonc" --mode yolo -p "$PROMPT"
else
  echo "SKIP: moca (no binary at $MOCA_BIN — set MOCA_BIN)"
  skip=$((skip + 1))
fi

# --- opencode ---------------------------------------------------------------
mkdir -p "$WORK/opencode/data" "$WORK/opencode/cfg"
if [ -x "$OPENCODE_BIN" ]; then
  probe opencode -- env \
    XDG_DATA_HOME="$WORK/opencode/data" \
    XDG_CONFIG_HOME="$WORK/opencode/cfg" \
    "$OPENCODE_BIN" run --standalone --format=json --auto --model "$ZEN_MODEL" "$PROMPT"
else
  echo "SKIP: opencode (no binary at $OPENCODE_BIN — set OPENCODE_BIN)"
  skip=$((skip + 1))
fi

# --- pi ---------------------------------------------------------------------
mkdir -p "$WORK/pi"
if [ -n "$PI_BIN" ]; then
  probe pi -- env \
    PI_CODING_AGENT_DIR="$WORK/pi" \
    "$PI_BIN" -p --model "$ZEN_MODEL" --no-session "$PROMPT"
else
  echo "SKIP: pi (not found — set PI_BIN)"
  skip=$((skip + 1))
fi

# --- claude code ------------------------------------------------------------
if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] || [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  mkdir -p "$WORK/claude"
  probe claude-code -- env CLAUDE_CONFIG_DIR="$WORK/claude" \
    "$CLAUDE_BIN" -p "$PROMPT" --output-format json --dangerously-skip-permissions
else
  echo "SKIP: claude-code (set ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN to probe)"
  skip=$((skip + 1))
fi

echo
echo "probes: $pass passed, $fail failed, $skip skipped"
[ "$fail" -eq 0 ]
