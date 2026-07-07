"""ACT — Agent Control Tower SDK.

A config-driven, harness-first agent SDK on top of pydantic-ai v2, with an
interface modelled after Anthropic's managed-agents API.

Core concepts
-------------
act.Agent         → create an agent object (mirrors ``agents.create``)
act.Session       → stateful conversation thread with full lifecycle management
act.coordinator   → multi-agent orchestration decorator
act.ACTCapability → lifecycle hooks for cross-cutting concerns
act.AgentConfig   → pydantic spec (YAML / JSON / inline)

Session lifecycle (mirrors managed-agents status machine)::

    idle → running → idle (end_turn)           # normal turn
                   → idle (requires_action)    # tool needs confirmation
                   → rescheduling → running    # transient error, auto-retry
                   → terminated               # fatal error

Quick start::

    import act
    from act import Agent, AgentConfig

    def lookup(user_id: str) -> str:
        return "Alice"

    agent = act.Agent(
        config=AgentConfig(name="greeter", model="claude-opus-4-8",
                           system="You are a friendly greeter."),
        tools=[lookup],
    )

    # Stateful session with full event stream
    session = act.Session(agent)
    async for event in session.run("Say hello to user 42"):
        match event:
            case act.AgentMessage(text=t, delta=True):
                print(t, end="", flush=True)
            case act.SessionIdle(stop_reason=r) if r.type == "end_turn":
                print()
            case act.SessionTerminated(error=e):
                print(f"Fatal: {e}")

    print(session.status)   # SessionStatus.IDLE
    print(session.usage)    # UsageStats(input_tokens=..., output_tokens=...)
"""

from act.agent import Agent
from act.config import AgentConfig, MCPServerConfig, ModelConfig, SkillConfig, ToolConfig
from act.events import (
    AgentMessage,
    CustomToolUse,
    Event,
    SessionError,
    SessionIdle,
    SessionRescheduling,
    SessionRunning,
    SessionTerminated,
    StopReason,
    ThinkingBlock,
    ToolConfirmationRequired,
    ToolResult,
    ToolUse,
    UsageUpdate,
)
from act.harness import ACTCapability, CompactionCapability, LoggingCapability
from act.multi_agent import coordinator
from act.session import Session, SessionArchivedError, SessionTerminatedError
from act.session_status import SessionStatus, UsageStats

__all__ = [
    # agent creation
    "Agent",
    "coordinator",
    # config
    "AgentConfig",
    "ModelConfig",
    "ToolConfig",
    "MCPServerConfig",
    "SkillConfig",
    # runtime
    "Session",
    "SessionStatus",
    "UsageStats",
    "SessionArchivedError",
    "SessionTerminatedError",
    # events
    "Event",
    "StopReason",
    "AgentMessage",
    "ToolUse",
    "CustomToolUse",
    "ToolResult",
    "ThinkingBlock",
    "SessionRunning",
    "SessionIdle",
    "SessionRescheduling",
    "SessionTerminated",
    "SessionError",
    "ToolConfirmationRequired",
    "UsageUpdate",
    # harness
    "ACTCapability",
    "CompactionCapability",
    "LoggingCapability",
]
