"""CompactionCapability — automatic conversation history compaction.

When cumulative token usage in a session crosses a threshold, this capability
summarises older messages with a lightweight LLM call and replaces them with
a single digest message, keeping only the most recent turns verbatim.

This mirrors Claude Code's /compact behaviour: the full history is compressed
into a summary so the agent can keep running long sessions without hitting
context limits.

How it works
------------
1. ``before_turn`` estimates the current history size in tokens (chars / 4).
2. If the estimate exceeds ``threshold_tokens``, ``_compact()`` is called.
3. ``_compact()`` formats the *older* messages as plain text and calls a
   cheap summarisation model (default: claude-haiku-4-5-20251001).
4. The session history is replaced with [summary_msg, ...last_n_turns].
5. ``on_compact`` is fired on all sibling capabilities.

Usage::

    from act.harness.compaction import CompactionCapability

    session = act.Session(
        agent,
        session_capabilities=[
            CompactionCapability(threshold_tokens=40_000, keep_last_n_turns=6),
        ],
    )

    async for event in session.run("..."):
        ...   # compaction happens silently before any turn that exceeds the threshold
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic_ai import Agent as _PydanticAgent
from pydantic_ai.messages import ModelRequest, UserPromptPart

from act.harness.capability import ACTCapability

if TYPE_CHECKING:
    from act.session import Session

_SUMMARISE_PROMPT = """\
You are a conversation summariser. Produce a concise but complete summary of
the conversation below. Preserve all key facts, decisions, tool calls and their
results, and any unresolved questions. The summary will be injected at the start
of a new context window so the agent can continue as if nothing was lost.

<conversation>
{conversation}
</conversation>

Return only the summary text — no preamble, no markdown fences."""


def _estimate_tokens(history: list) -> int:
    """Rough token estimate: total character count of all message text / 4."""
    total_chars = 0
    for msg in history:
        for part in getattr(msg, "parts", []):
            content = getattr(part, "content", "") or getattr(part, "text", "") or ""
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for block in content:
                    total_chars += len(getattr(block, "text", "") or "")
    return total_chars // 4


def _messages_to_text(history: list) -> str:
    """Render history as plain text for the summariser."""
    lines: list[str] = []
    for msg in history:
        role = "assistant" if msg.__class__.__name__ == "ModelResponse" else "user"
        for part in getattr(msg, "parts", []):
            content = (
                getattr(part, "content", None)
                or getattr(part, "text", None)
                or ""
            )
            if isinstance(content, list):
                content = " ".join(getattr(b, "text", "") for b in content)
            if content:
                lines.append(f"[{role}]: {content.strip()}")
    return "\n".join(lines)


class CompactionCapability(ACTCapability):
    """Automatically compact conversation history when it grows too large.

    Parameters
    ----------
    threshold_tokens:
        Estimated token count at which compaction is triggered.
        Default 40 000 — safe for most 200k-context models.
    keep_last_n_turns:
        Number of most-recent *pairs* (user + assistant) to keep verbatim.
        The rest are summarised. Default 6.
    summary_model:
        Model used for the summarisation call. A cheap/fast model is ideal.
        Default ``claude-haiku-4-5-20251001``.
    """

    def __init__(
        self,
        threshold_tokens: int = 40_000,
        keep_last_n_turns: int = 6,
        summary_model: str = "claude-haiku-4-5-20251001",
    ) -> None:
        self.threshold_tokens = threshold_tokens
        self.keep_last_n_turns = keep_last_n_turns
        self.summary_model = summary_model
        self._summariser = _PydanticAgent(model=summary_model)

    async def before_turn(self, session: "Session", user_input: str) -> str:
        if _estimate_tokens(session._history) >= self.threshold_tokens:
            await self._compact(session)
        return user_input

    async def _compact(self, session: "Session") -> None:
        history = session._history
        # Keep the last keep_last_n_turns * 2 messages verbatim (user + assistant pairs)
        keep_n = self.keep_last_n_turns * 2
        old_messages = history[:-keep_n] if len(history) > keep_n else []
        recent_messages = history[-keep_n:] if len(history) > keep_n else history

        if not old_messages:
            return

        conversation_text = _messages_to_text(old_messages)
        prompt = _SUMMARISE_PROMPT.format(conversation=conversation_text)
        result = await self._summariser.run(prompt)
        summary = result.output.strip()

        # Build a single synthetic user message that carries the summary
        summary_msg = ModelRequest(parts=[
            UserPromptPart(
                content=(
                    f"[Prior conversation summary — treat this as established context]\n\n"
                    f"{summary}"
                )
            )
        ])

        session._history = [summary_msg, *recent_messages]

        # Notify sibling capabilities
        for cap in getattr(session, "_session_capabilities", []):
            if cap is not self:
                await cap.on_compact(session, summary)
