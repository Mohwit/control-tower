"""Example 08 — Pluggable harness capabilities.

Demonstrates the two capability layers:

  ACTCapability      → pydantic-ai level (LoggingCapability)
  SessionCapability  → ACT Session level (CompactionCapability + custom)

Run:
    uv run python examples/08_capabilities.py
"""

import asyncio
import act
from act import AgentConfig, ACTCapability
from act.harness.compaction import CompactionCapability
from act.harness.logging import LoggingCapability


# ---------------------------------------------------------------------------
# Custom capability — example of writing your own
# ---------------------------------------------------------------------------

class TurnBudgetCapability(ACTCapability):
    """Warn (and optionally stop) after a max number of turns."""

    def __init__(self, max_turns: int = 5) -> None:
        self.max_turns = max_turns

    async def before_turn(self, session, user_input: str) -> str:
        if session.turn_count >= self.max_turns:
            raise RuntimeError(
                f"Turn budget exceeded ({self.max_turns} turns). "
                "Archive the session or start a new one."
            )
        return user_input  # pass through unmodified

    async def after_turn(self, session) -> None:
        remaining = self.max_turns - session.turn_count
        print(f"[budget] {remaining} turn(s) remaining")

    async def on_compact(self, session, summary: str) -> None:
        print(f"[budget] history compacted — summary length={len(summary)} chars")


# ---------------------------------------------------------------------------
# Agent setup
# ---------------------------------------------------------------------------

def word_count(text: str) -> int:
    """Count words in text."""
    return len(text.split())


agent = act.Agent(
    config=AgentConfig(
        name="demo-agent",
        model="claude-haiku-4-5-20251001",
        system="You are a concise assistant. Keep replies to 2-3 sentences.",
    ),
    tools=[word_count],
    # ACTCapability: pydantic-ai level (logs every tool call + run timing)
    capabilities=[LoggingCapability(prefix="[log]")],
)


# ---------------------------------------------------------------------------
# Session with pluggable SessionCapabilities
# ---------------------------------------------------------------------------

session = act.Session(
    agent,
    capabilities=[
        CompactionCapability(threshold_tokens=500, keep_last_n_turns=2),
        TurnBudgetCapability(max_turns=10),
    ],
)


async def main() -> None:
    questions = [
        "What is the capital of France?",
        "How many words are in 'the quick brown fox'?",
        "Tell me a one-sentence fact about Paris.",
    ]

    for q in questions:
        print(f"\nUser: {q}")
        async for event in session.run(q):
            match event:
                case act.AgentMessage(text=t, delta=True):
                    print(t, end="", flush=True)
                case act.SessionIdle(stop_reason=r) if r.type == "end_turn":
                    print()
                case act.SessionTerminated(error=e):
                    print(f"\nFatal: {e}")


if __name__ == "__main__":
    asyncio.run(main())
