"""Harbor adapter for OpenCode v2 — https://github.com/anomalyco/opencode.

Harbor 0.24.0's built-in ``opencode`` agent targets OpenCode v1 and cannot
drive v2: the npm package was renamed (``opencode-ai`` → ``@opencode/cli``)
and the CLI surface moved (``--model`` is a ``run`` flag now — a global
``--model`` is rejected; ``--dangerously-skip-permissions`` was replaced by
``--auto``; headless runs need ``--standalone`` so ``run`` starts a private
server instead of attaching to the background service).

This subclass overrides exactly ``install()`` and ``run()`` to close that
gap. Everything else is inherited from
``harbor.agents.installed.opencode.OpenCode`` and required no change —
verified against a real v2.0.30 run before the benchmark:

* the ``run --format=json`` event stream is unchanged in v2 (same
  ``step_start`` / ``tool_use`` / ``step_finish`` events; ``step_finish.part``
  still carries ``tokens``/``cost``), so trajectory conversion and metric
  backfill (``populate_context_post_run``) work as-is;
* provider/model/auth plumbing is unchanged in practice: the built-in
  ``opencode-go`` provider authenticates from the ``OPENCODE_API_KEY``
  environment variable, and the ``opencode.json`` the base class writes
  (provider ``models`` registration) is read by v2 and harmless.

Install deviations from upstream's command, both deliberate:

* package name ``@opencode/cli`` (upstream installs ``opencode-ai``), and
* an explicit ``postinstall.mjs`` invocation after ``npm i -g``: the
  platform binary is swapped in by the package's own postinstall, and
  npm ≥ 12 blocks install scripts unless they are allow-listed
  (``allowScripts``), so run it explicitly — it is idempotent.

The agent name stays ``opencode`` (same as upstream) so results remain
comparable across runs; the pinned version travels in ``kwargs.version``.
"""
from __future__ import annotations

import shlex

from harbor.agents.installed.base import (
    NonZeroAgentExitCodeError,
    with_prompt_template,
)
from harbor.agents.installed.node_install import nvm_node_install_snippet
from harbor.agents.installed.opencode import OpenCode as _UpstreamOpenCode
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

_PACKAGE = "@opencode/cli"


class OpenCodeV2(_UpstreamOpenCode):
    """OpenCode v2 (``@opencode/cli``) driven through Harbor's OpenCode agent."""

    async def install(self, environment: BaseEnvironment) -> None:
        # `nodejs`/`npm` cover musl images, where nvm cannot be used;
        # `coreutils` provides the `stdbuf` that run() pipes through.
        await self.ensure_system_dependencies(
            environment, ("curl", "bash", "coreutils", "nodejs", "npm")
        )
        version_spec = f"@{self._version}" if self._version else "@latest"
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                "if ldd --version 2>&1 | grep -qi musl || "
                "[ -f /etc/alpine-release ]; then "
                "node --version && npm --version; "
                f"else {nvm_node_install_snippet()}; fi && "
                f"npm i -g {_PACKAGE}{version_spec} && "
                # npm >= 12 blocks install scripts (allowScripts policy) and
                # the platform binary is swapped in by the package's own
                # postinstall — run it explicitly (idempotent).
                f'node "$(npm root -g)/{_PACKAGE}/postinstall.mjs" && '
                "opencode --version"
            ),
        )

    @with_prompt_template
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        # Capture the rendered instruction so the trajectory can include the
        # user turn even when OpenCode's run stream omits it.
        self._instruction = instruction
        escaped_instruction = shlex.quote(instruction)

        if not self.model_name or "/" not in self.model_name:
            raise ValueError("Model name must be in the format provider/model_name")

        env = dict(self.model_connection.env)

        # Enable fake VCS for OpenCode
        env["OPENCODE_FAKE_VCS"] = "git"
        env["XDG_DATA_HOME"] = (
            self.environment_logs_dir / "opencode" / "xdg-data"
        ).as_posix()
        env["XDG_STATE_HOME"] = (
            self.environment_logs_dir / "opencode" / "xdg-state"
        ).as_posix()

        skills_command = self._build_register_skills_command()
        if skills_command:
            await self.exec_as_agent(environment, command=skills_command, env=env)

        mcp_command = self._build_register_config_command()
        if mcp_command:
            await self.exec_as_agent(environment, command=mcp_command, env=env)

        cli_flags = self.build_cli_flags()
        cli_flags_arg = (cli_flags + " ") if cli_flags else ""
        resume_flag = "--continue " if self._resume else ""

        await self.exec_as_agent(
            environment,
            # v2 command shape (verified on 2.0.30): `--model` is a run flag,
            # permissions go through `--auto` (v1's
            # `--dangerously-skip-permissions` is gone), and `--standalone`
            # starts a private server instead of the background service.
            # The --thinking flag means thinking blocks appear in the JSON.
            command=(
                "[ -f ~/.nvm/nvm.sh ] && . ~/.nvm/nvm.sh; "
                f"opencode run --standalone --format=json "
                f"{resume_flag}{cli_flags_arg}--thinking --auto "
                f"--model={self.model_name} -- {escaped_instruction} "
                f"2>&1 </dev/null | stdbuf -oL tee "
                f"{shlex.quote((self.environment_logs_dir / self._OUTPUT_FILENAME).as_posix())}"
            ),
            env=env,
        )

        if messages := self._error_messages():
            raise NonZeroAgentExitCodeError(
                "OpenCode emitted error event(s): " + "; ".join(messages[:3])
            )
