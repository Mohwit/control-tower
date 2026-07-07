"""ACTCapability — base class for ACT harness extensions.

Every cross-cutting concern in the ACT harness is a capability: logging,
tracing, cost tracking, guardrails, rate-limiting, PII redaction, etc.
Capabilities are stateless by default but may hold config state.

They plug into pydantic-ai's ``AbstractCapability`` lifecycle hook system and
are passed via ``capabilities=[...]`` on ``@act.agent`` or ``@act.coordinator``.

Lifecycle hooks available (override any subset)
------------------------------------------------
Run level:
  before_run(ctx)                          — before any model or tool call
  after_run(ctx, result)                   — after the full run completes

Node level (internal graph nodes):
  before_node(ctx, node)                   — before each graph node
  after_node(ctx, node)                    — after each graph node

Model request level:
  wrap_model_request(ctx, call_next)       — wrap the LLM call (middleware pattern)
  on_model_request_error(ctx, exc)         — handle / log model errors

Tool level:
  before_tool_validate(ctx, tool, args)    — before argument validation
  after_tool_validate(ctx, tool, args)     — after argument validation
  before_tool_execute(ctx, tool, args)     — before tool execution
  after_tool_execute(ctx, tool, args, ret) — after tool execution

Output level:
  before_output_validate(ctx, output)      — before output validation
  after_output_validate(ctx, output)       — after output validation

Usage — simple logging capability::

    from act import ACTCapability

    class AuditCapability(ACTCapability):
        async def before_run(self, ctx):
            print(f"[audit] run started  agent={ctx.agent.name}")

        async def after_run(self, ctx, result):
            print(f"[audit] run finished tokens={result.usage().total_tokens}")

        async def before_tool_execute(self, ctx, tool, args):
            print(f"[audit] tool={tool.name} args={args}")

    @act.agent(
        config=AgentConfig(name="my-agent", model="claude-opus-4-8"),
        capabilities=[AuditCapability()],
    )
    class MyAgent:
        ...

Usage — wrap model request (middleware)::

    class TimingCapability(ACTCapability):
        async def wrap_model_request(self, ctx, call_next):
            import time
            t0 = time.perf_counter()
            result = await call_next(ctx)
            print(f"model latency: {time.perf_counter() - t0:.2f}s")
            return result
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_ai.capabilities.abstract import AbstractCapability

if TYPE_CHECKING:
    from act.session import Session


class ACTCapability(AbstractCapability):
    """Base class for all ACT harness capabilities.

    Covers both pydantic-ai lifecycle hooks (model requests, tool calls) and
    ACT Session lifecycle hooks (conversation turns, compaction).

    Pass instances via ``capabilities=[...]`` on ``act.Session`` or ``act.Agent``.
    All hooks are no-ops by default — override only what you need.

    Session-level hooks
    -------------------
    before_turn(session, user_input) -> str   called before each turn; may rewrite input
    after_turn(session)                       called after a clean end_turn
    on_compact(session, summary)              called when compaction rewrites history

    Pydantic-ai hooks (inherited from AbstractCapability)
    ------------------------------------------------------
    before_run / after_run
    wrap_model_request / on_model_request_error
    before_tool_execute / after_tool_execute
    before_output_validate / after_output_validate
    """

    async def before_turn(self, session: "Session", user_input: str) -> str:
        """Called before each Session turn. Return (possibly modified) user_input."""
        return user_input

    async def after_turn(self, session: "Session") -> None:
        """Called after a turn ends cleanly (end_turn). Not called on interrupt/error."""

    async def on_compact(self, session: "Session", summary: str) -> None:
        """Called when compaction replaces history with a digest."""
