"""Example 05 — Custom harness capability.

ACTCapability hooks into pydantic-ai's AbstractCapability lifecycle.
Stack multiple capabilities by passing a list.

Demonstrates:
  - AuditCapability  — logs every run start/end with token usage
  - TimingCapability — measures model request latency
  - CostGuard        — raises if estimated cost exceeds a budget
"""

import asyncio
import time
from typing import Any

import act
from act import ACTCapability, AgentConfig, ModelConfig


class AuditCapability(ACTCapability):
    """Logs run start, end, and each tool call."""

    async def before_run(self, ctx) -> None:
        print(f"[audit] ▶ run started   agent={ctx.agent.name}")

    async def after_run(self, ctx, result) -> None:
        usage = result.usage()
        print(
            f"[audit] ■ run complete  agent={ctx.agent.name} "
            f"tokens={usage.total_tokens}"
        )

    async def before_tool_execute(self, ctx, tool, args) -> None:
        print(f"[audit]   tool_call={tool.name} args={args}")

    async def after_tool_execute(self, ctx, tool, args, ret) -> None:
        print(f"[audit]   tool_ret={tool.name} → {ret!r}")


class TimingCapability(ACTCapability):
    """Measures and logs LLM request latency."""

    async def wrap_model_request(self, ctx, call_next) -> Any:
        t0 = time.perf_counter()
        result = await call_next(ctx)
        elapsed = time.perf_counter() - t0
        print(f"[timing] model latency: {elapsed:.2f}s")
        return result


class CostGuard(ACTCapability):
    """Raises RuntimeError if total_tokens exceeds the configured budget."""

    def __init__(self, max_tokens: int) -> None:
        self.max_tokens = max_tokens

    async def after_run(self, ctx, result) -> None:
        used = result.usage().total_tokens
        if used > self.max_tokens:
            raise RuntimeError(
                f"CostGuard: run used {used} tokens, budget is {self.max_tokens}"
            )
        print(f"[cost]   {used}/{self.max_tokens} tokens used ({used/self.max_tokens:.0%})")


def get_info(topic: str) -> str:
    return f"Here is information about {topic}: [mock data]"


monitored = act.Agent(
    config=AgentConfig(
        name="monitored-agent",
        model=ModelConfig(id="claude-opus-4-8"),
        system="You are a helpful assistant.",
    ),
    tools=[get_info],
    capabilities=[
        AuditCapability(),
        TimingCapability(),
        CostGuard(max_tokens=5000),
    ],
)


async def main():
    result = await monitored.run("Tell me about the Eiffel Tower.")
    print(f"\nOutput: {result.output}")


if __name__ == "__main__":
    asyncio.run(main())
