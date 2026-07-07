"""LoggingCapability — structured console logging for agent runs.

An ``ACTCapability`` (pydantic-ai level) that logs run start/end, every tool
call, and model errors. Useful as a reference for writing your own capabilities.

Usage::

    from act.harness.logging import LoggingCapability

    agent = act.Agent(
        config=AgentConfig(name="my-agent", model="claude-sonnet-4-6"),
        tools=[...],
        capabilities=[LoggingCapability()],
    )
"""

from __future__ import annotations

import time

from act.harness.capability import ACTCapability


class LoggingCapability(ACTCapability):
    """Structured logging at the pydantic-ai model/tool lifecycle level.

    Parameters
    ----------
    prefix:
        String prepended to every log line. Default ``"[act]"``.
    log_tools:
        Whether to log tool calls. Default True.
    """

    def __init__(self, prefix: str = "[act]", *, log_tools: bool = True) -> None:
        self.prefix = prefix
        self.log_tools = log_tools
        self._t0: float | None = None

    def _log(self, msg: str) -> None:
        print(f"{self.prefix} {msg}")

    async def before_run(self, ctx) -> None:
        self._t0 = time.perf_counter()
        agent_name = getattr(ctx, "agent", None)
        name = getattr(agent_name, "name", "unknown") if agent_name else "unknown"
        self._log(f"run started  agent={name!r}")

    async def after_run(self, ctx, result) -> None:
        elapsed = time.perf_counter() - (self._t0 or 0)
        usage = result.usage() if callable(getattr(result, "usage", None)) else None
        tokens = getattr(usage, "total_tokens", "?") if usage else "?"
        self._log(f"run finished  elapsed={elapsed:.2f}s  tokens={tokens}")

    async def before_tool_execute(self, ctx, tool, args) -> None:
        if self.log_tools:
            self._log(f"tool call  name={tool.name!r}  args={args}")

    async def after_tool_execute(self, ctx, tool, args, ret) -> None:
        if self.log_tools:
            preview = str(ret)[:120]
            self._log(f"tool done  name={tool.name!r}  result={preview!r}")

    async def on_model_request_error(self, ctx, exc) -> None:
        self._log(f"model error  {type(exc).__name__}: {exc}")
