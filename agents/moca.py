"""Harbor adapter for moca — https://github.com/adeotek/moca.

moca is a minimal, token-efficient, provider-agnostic coding agent shipped as
a single static Go binary. Headless runs use ``moca -p <prompt>`` and exit
non-zero when the run does not complete.

This integration (``BaseInstalledAgent``):

* installs a pinned release package (``.tar.gz``, verified against the
  release's ``checksums.txt``),
* writes a minimal ``~/.config/moca/config.jsonc`` naming the model,
  referencing the API key by environment-variable indirection
  (``env:OPENCODE_API_KEY``) — the key itself is never written to disk — and
  setting ``context.maxSteps`` (the tool-batch budget before moca takes its
  tool-less wrap-up turn and exits 3 as "incomplete"),
* runs ``moca --mode yolo -p <instruction>`` (the v0.4.0 permission-mode
  overhaul replaced the ``--yolo`` flag; older pinned versions are driven with
  ``--yolo`` — see ``permission_flags``), teeing output into the trial logs
  and copying the session transcript alongside them, and
* backfills token/cost usage from the session JSONL
  (``populate_context_post_run``).

Credentials: one variable, ``OPENCODE_API_KEY``, for every zen agent in the
bench. It is moca's own built-in default for the ``opencode-go`` provider
(``config.BuiltinProviders``), and OpenCode and Pi read the same name, so the
whole sweep can be driven by a single key in the agent phase
(``harbor run ... --ae OPENCODE_API_KEY=...``). The providers block below
spells the reference out rather than relying on that default: it keeps the
adapter working for a custom ``ZEN_MODEL`` provider and makes the indirection
visible in the generated config.
"""
from __future__ import annotations

import json
import logging
import shlex

from pydantic import Field

from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template

# Harbor 0.25 replaced ModelConnectionSpec's api_key_envs with an explicit
# ProviderAccess; the credential is both read from and written to the same env
# name because moca's config only ever references env:OPENCODE_API_KEY.
from harbor.agents.agent_auth_resolution import ModelConnectionSpec, ProviderAccess
from harbor.agents.options import InstalledAgentOptions
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

_GITHUB_REPO = "adeotek/moca"
_DEFAULT_VERSION = "v0.7.11"
_DEFAULT_MAX_STEPS = 250
# The v0.4.0 permission-mode overhaul replaced the legacy --yolo flag with
# `--mode yolo`; version bisects must speak both dialects.
_MODE_FLAG_SINCE = (0, 4)
_OUTPUT_FILENAME = "moca.txt"
_SESSION_FILENAME = "moca-session.jsonl"
# Name of the agent-phase env var holding the provider API key; the generated
# config references it through moca's `env:` indirection. One name for the
# whole bench: moca's own default for opencode-go, and what OpenCode/Pi read.
_API_KEY_ENV = "OPENCODE_API_KEY"

log = logging.getLogger(__name__)


def permission_flags(version: str | None, mode: str) -> str:
    """Permission flags for a pinned moca version: ``--mode <m>`` on
    v0.4.0+, the legacy ``--yolo`` on v0.3.x (its only permission flag)."""
    if not mode:
        return ""
    raw = (version or _DEFAULT_VERSION).lstrip("v")
    try:
        major, minor = (int(part.split("-")[0]) for part in raw.split(".")[:2])
    except (AttributeError, TypeError, ValueError):
        major, minor = _MODE_FLAG_SINCE  # unparsable → assume current CLI
    if (major, minor) >= _MODE_FLAG_SINCE:
        return f"--mode {shlex.quote(mode)} "
    if mode != "yolo":
        raise ValueError(
            f"moca {version}: only --yolo exists below v0.4.0 (asked for mode {mode!r})"
        )
    return "--yolo "


class MocaOptions(InstalledAgentOptions):
    """``--ak`` options accepted by the moca integration."""

    mode: str = Field(
        default="yolo",
        description=(
            "Permission mode for the run: default | auto | yolo | plan "
            "(empty string omits the flag)."
        ),
    )
    max_steps: int = Field(
        default=_DEFAULT_MAX_STEPS,
        description=(
            "context.maxSteps written into the generated config — the "
            "tool-batch budget before moca's tool-less wrap-up turn and "
            "exit 3. moca's own default is 40."
        ),
    )


def run_command(instruction: str, flags: str, log_path: str, session_copy: str) -> str:
    """The shell line Harbor executes for one moca run.

    Two jobs beyond launching moca: capture the exit code across the tee pipe
    portably (a subshell writes it to a temp file — no shell-dependent
    PIPESTATUS), and keep a session transcript in the logs directory. The
    transcript carries the token/cost accounting and moca writes it under
    ``$HOME/.local/share/moca/sessions/``, but the copy at the end of this line
    never runs when Harbor kills the agent phase (a 900 s timeout, a cancel),
    so a background mirror refreshes the copy every few seconds while the run
    is in flight. A mirror copy caught mid-append is still usable — the
    metrics reader skips an unparseable line — and the final copy below
    replaces it after a clean exit.
    """
    newest = 'sess="$(ls -t "$HOME/.local/share/moca/sessions/"*.jsonl 2>/dev/null | head -n1)"; '
    return (
        'export PATH="$HOME/.local/bin:$PATH"; '
        "( while :; do " + newest + f'[ -n "$sess" ] && cp "$sess" {shlex.quote(session_copy)}; '
        "sleep 5; done ) 2>/dev/null & "
        "moca_mirror_pid=$!; "
        # Wrap moca in a subshell so its exit code survives the tee pipe.
        f'( moca --config "$HOME/.config/moca/config.jsonc" {flags}'
        f" -p {shlex.quote(instruction)} 2>&1; echo $? >/tmp/moca.exit )"
        f" | tee {shlex.quote(log_path)}; "
        "code=$(cat /tmp/moca.exit); "
        'kill "$moca_mirror_pid" 2>/dev/null; '
        + newest
        + f'[ -n "$sess" ] && cp "$sess" {shlex.quote(session_copy)}; '
        "exit $code"
    )


class Moca(BaseInstalledAgent):
    """Run the moca CLI inside the task environment."""

    MODEL_CONNECTION = ModelConnectionSpec(
        agent_provider_access=ProviderAccess(
            api_key_candidate_names=[_API_KEY_ENV],
        ),
        api_key_destination_names={"default": _API_KEY_ENV},
    )

    options_model = MocaOptions
    options: MocaOptions

    @staticmethod
    def name() -> str:
        return "moca"

    def get_version_command(self) -> str | None:
        return 'export PATH="$HOME/.local/bin:$PATH"; moca --version'

    async def install(self, environment: BaseEnvironment) -> None:
        await self.ensure_system_dependencies(
            environment, ("curl", "bash", "tar", "coreutils")
        )
        version = self._version or _DEFAULT_VERSION
        if not version.startswith("v"):
            version = f"v{version}"
        base = f"https://github.com/{_GITHUB_REPO}/releases/download/{version}"
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                'mkdir -p "$HOME/.local/bin"; '
                'case "$(uname -m)" in '
                "  x86_64) arch=amd64 ;; "
                "  aarch64|arm64) arch=arm64 ;; "
                '  *) echo "moca: unsupported architecture $(uname -m)" >&2; exit 1 ;; '
                "esac; "
                f'base="{base}"; tar_name="moca-{version}-linux-$arch.tar.gz"; '
                # Keep the release asset's own filename: `sha256sum -c` looks
                # up the checksums.txt entry's filename in the cwd.
                'curl -fsSL "$base/$tar_name" -o "/tmp/$tar_name"; '
                'curl -fsSL "$base/checksums.txt" -o /tmp/moca-checksums.txt; '
                '( cd /tmp && grep -E "[ *]$tar_name$" moca-checksums.txt | sha256sum -c - ); '
                'tar -xzf "/tmp/$tar_name" -C "$HOME/.local/bin" moca; '
                'chmod +x "$HOME/.local/bin/moca"; '
                'rm -f "/tmp/$tar_name" /tmp/moca-checksums.txt; '
                'export PATH="$HOME/.local/bin:$PATH"; moca --version'
            ),
        )

    @with_prompt_template
    async def run(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        if not self.model_name or "/" not in self.model_name:
            raise ValueError(
                "moca requires -m provider/model (e.g. opencode-go/deepseek-v4.1-flash)"
            )
        provider = self.model_name.split("/", 1)[0]

        # Minimal config; the key is referenced, never embedded. maxSteps
        # bounds the run's tool batches (moca exits 3 when it runs out).
        config = {
            "model": self.model_name,
            "providers": {provider: {"apiKey": f"env:{_API_KEY_ENV}"}},
            "context": {"maxSteps": self.options.max_steps},
        }
        env = dict(self.model_connection.env)
        await self.exec_as_agent(
            environment,
            command=(
                'mkdir -p "$HOME/.config/moca" && '
                f"printf '%s' {shlex.quote(json.dumps(config))} "
                '> "$HOME/.config/moca/config.jsonc"'
            ),
            env=env,
        )

        log_path = (self.environment_logs_dir / _OUTPUT_FILENAME).as_posix()
        session_copy = (self.environment_logs_dir / _SESSION_FILENAME).as_posix()
        flags = permission_flags(self._version, self.options.mode)
        await self.exec_as_agent(
            environment,
            command=run_command(instruction, flags, log_path, session_copy),
            env=env,
        )

    def populate_context_post_run(self, context: AgentContext) -> None:
        """Sum token usage and cost from the session JSONL synced with the logs."""
        path = self.logs_dir / _SESSION_FILENAME
        if not path.exists():
            log.warning(
                "no moca session transcript in the logs dir (%s): token and cost "
                "metrics are unavailable for this trial — the agent phase was "
                "most likely killed (timeout or cancel) before its final copy",
                path,
            )
            return
        input_tokens = output_tokens = cache_read = cache_write = 0
        cost = 0.0
        for line in path.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            usage = entry.get("usage")
            if isinstance(usage, dict):
                input_tokens += int(usage.get("input") or 0)
                output_tokens += int(usage.get("output") or 0)
                cache_read += int(usage.get("cacheRead") or 0)
                cache_write += int(usage.get("cacheWrite") or 0)
            cost_value = entry.get("cost")
            if isinstance(cost_value, (int, float)):
                cost += float(cost_value)
        context.n_input_tokens = input_tokens + cache_read + cache_write
        context.n_output_tokens = output_tokens
        context.n_cache_tokens = cache_read
        context.cost_usd = cost if cost > 0 else None
