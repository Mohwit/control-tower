"""ACT event types — mirrors managed-agents SSE event vocabulary.

All events are plain dataclasses so they work cleanly with ``match`` statements.

Lifecycle sequence for a normal turn::

    SessionRunning()
    AgentMessage(delta=True) × N          # streaming text chunks
    SessionIdle(stop_reason=StopReason("end_turn"))

For a tool-confirmation pause::

    SessionRunning()
    ToolConfirmationRequired(...)         # emitted before each blocked tool
    SessionIdle(stop_reason=StopReason("requires_action", event_ids=[...]))
    # caller calls session.confirm_tool() or session.deny_tool()
    AgentMessage(delta=True) × N          # agent continues after confirmation
    SessionIdle(stop_reason=StopReason("end_turn"))

For a transient error (auto retry)::

    SessionRunning()
    SessionRescheduling(attempt=1)        # retrying automatically
    AgentMessage(delta=True) × N
    SessionIdle(stop_reason=StopReason("end_turn"))

For a fatal error::

    SessionRunning()
    SessionError(message=..., retry_status="non_retryable")
    SessionTerminated(error=...)

Managed-agents mapping
----------------------
``agent.message``              → AgentMessage
``agent.tool_use``             → ToolUse
``agent.custom_tool_use``      → CustomToolUse
``agent.tool_result``          → ToolResult
``agent.thinking``             → ThinkingBlock
``session.status_running``     → SessionRunning
``session.status_idle``        → SessionIdle
``session.status_rescheduled`` → SessionRescheduling
``session.status_terminated``  → SessionTerminated
``session.error``              → SessionError
``user.tool_confirmation``     → (send-side) SessionIdle(requires_action) triggers
``span.model_request_end``     → UsageUpdate
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Stop reason (carried by SessionIdle)
# ---------------------------------------------------------------------------

@dataclass
class StopReason:
    """Why the agent stopped — mirrors managed-agents stop_reason object."""
    type: Literal["end_turn", "requires_action", "interrupted"]
    event_ids: list[str] = field(default_factory=list)
    """Populated for ``requires_action``: IDs of pending confirmation requests."""


# ---------------------------------------------------------------------------
# Agent content events
# ---------------------------------------------------------------------------

@dataclass
class AgentMessage:
    """Text output from the agent.

    ``delta=True`` → streaming chunk (part of the current response).
    ``delta=False`` → full final text (e.g. from a non-streaming run).
    """
    text: str
    delta: bool = False


@dataclass
class ToolUse:
    """Agent invoked a built-in tool."""
    tool_name: str
    tool_use_id: str
    input: dict[str, Any]


@dataclass
class CustomToolUse:
    """Agent invoked a custom tool defined in your system (you must execute it)."""
    tool_name: str
    tool_use_id: str
    input: dict[str, Any]


@dataclass
class ToolResult:
    """Result of a tool execution."""
    tool_name: str
    tool_use_id: str
    output: Any
    is_error: bool = False


@dataclass
class ThinkingBlock:
    """Agent extended-thinking content (claude-opus-4-8 with thinking enabled)."""
    text: str


# ---------------------------------------------------------------------------
# Session lifecycle events
# ---------------------------------------------------------------------------

@dataclass
class SessionRunning:
    """Agent is actively executing. Emitted at the start of each turn.
    Mirrors ``session.status_running``.
    """


@dataclass
class SessionIdle:
    """Agent finished its current task and is waiting for input.
    Mirrors ``session.status_idle``.

    ``stop_reason.type`` values:

    - ``end_turn``        — agent finished naturally
    - ``requires_action`` — paused, waiting for tool confirmation(s).
      ``stop_reason.event_ids`` contains the pending ``tool_use_id`` values.
    - ``interrupted``     — caller called ``session.interrupt()``
    """
    stop_reason: StopReason
    usage: dict[str, Any] | None = None


@dataclass
class SessionRescheduling:
    """Transient error occurred; session is retrying automatically.
    Mirrors ``session.status_rescheduled``.

    No action required — the run will continue. Subsequent retries may
    succeed once the transient condition clears.
    """
    error: str | None = None
    attempt: int = 1


@dataclass
class SessionTerminated:
    """Unrecoverable error — session is permanently ended.
    Mirrors ``session.status_terminated``.

    Create a new ``Session`` to continue. History from this session can be
    loaded via ``Session.load()`` for continuity.
    """
    error: str | None = None


@dataclass
class SessionError:
    """Observability event fired alongside status transitions on error.
    Mirrors ``session.error``.

    ``retry_status``: ``"retryable"`` (leads to rescheduling) or
    ``"non_retryable"`` (leads to terminated).
    """
    message: str
    retry_status: str | None = None


# ---------------------------------------------------------------------------
# Human-in-the-loop
# ---------------------------------------------------------------------------

@dataclass
class ToolConfirmationRequired:
    """Session paused — a tool with ``always_ask`` policy needs approval.

    Respond by calling ``session.confirm_tool(tool_use_id)`` to allow or
    ``session.deny_tool(tool_use_id)`` to deny. The session resumes once
    all pending confirmations are resolved.

    Mirrors the ``agent.tool_use`` + ``session.status_idle(requires_action)``
    pair in managed-agents.
    """
    tool_use_id: str
    tool_name: str
    input: dict[str, Any]


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------

@dataclass
class UsageUpdate:
    """Token usage for the just-completed model call.
    Mirrors ``span.model_request_end``.
    """
    input_tokens: int
    output_tokens: int
    total_tokens: int


# ---------------------------------------------------------------------------
# Union type — for exhaustive match statements
# ---------------------------------------------------------------------------

Event = (
    AgentMessage
    | ToolUse
    | CustomToolUse
    | ToolResult
    | ThinkingBlock
    | SessionRunning
    | SessionIdle
    | SessionRescheduling
    | SessionTerminated
    | SessionError
    | ToolConfirmationRequired
    | UsageUpdate
)
