"""Example 07 — Tool confirmation: requires_action and interrupt.

Covers all session lifecycle states:
  idle          → session starts in idle
  running       → agent is executing
  rescheduling  → transient error, auto-retry (simulated)
  terminated    → fatal error, session ended permanently

And both confirmation styles:
  A. Callback-based  — synchronous/async callback decides allow/deny
  B. Event-driven    — ToolConfirmationRequired events + confirm_tool/deny_tool
"""

import asyncio
import act
from act import AgentConfig, ModelConfig, ToolConfig, ToolPermission


# ---------------------------------------------------------------------------
# Tools — some marked always_ask in AgentConfig
# ---------------------------------------------------------------------------

def read_file(path: str) -> str:
    """Read a file from disk."""
    return f"[contents of {path}]"


def delete_file(path: str) -> str:
    """Permanently delete a file."""
    return f"Deleted {path}."


def write_file(path: str, content: str) -> str:
    """Write content to a file."""
    return f"Written {len(content)} bytes to {path}."


# Config: read_file is auto, delete_file and write_file require confirmation
fs_agent = act.Agent(
    config=AgentConfig(
        name="filesystem-agent",
        model=ModelConfig(id="claude-opus-4-8"),
        system="You are a filesystem assistant. Always confirm before destructive operations.",
        tools=[
            ToolConfig(name="read_file"),                                         # auto
            ToolConfig(name="delete_file", permission_policy=ToolPermission(type="always_ask")),
            ToolConfig(name="write_file",  permission_policy=ToolPermission(type="always_ask")),
        ],
    ),
    tools=[read_file, delete_file, write_file],
)


# ---------------------------------------------------------------------------
# Pattern A — Callback-based confirmation
# ---------------------------------------------------------------------------

async def run_with_callback():
    print("\n=== Pattern A: Callback-based confirmation ===")

    async def confirm(tool_name: str, args: dict) -> bool:
        print(f"\n  [confirm] {tool_name}({args}) → ", end="")
        # Allow write, deny delete
        allowed = tool_name != "delete_file"
        print("allow" if allowed else "DENY")
        return allowed

    session = act.Session(fs_agent, on_tool_confirmation=confirm)
    print(f"Status: {session.status}")

    async for event in session.run("Read config.yaml, then delete it and write a backup."):
        match event:
            case act.AgentMessage(text=t, delta=True):
                print(t, end="", flush=True)
            case act.SessionRunning():
                print(f"\n[running]")
            case act.SessionIdle(stop_reason=r):
                print(f"\n[idle: {r.type}]")
                if r.type == "end_turn":
                    break


# ---------------------------------------------------------------------------
# Pattern B — Event-driven confirmation (requires_action)
# ---------------------------------------------------------------------------

async def run_with_events():
    print("\n=== Pattern B: Event-driven confirmation (requires_action) ===")

    session = act.Session(fs_agent)  # no callback — emits ToolConfirmationRequired events
    print(f"Status: {session.status}")

    async for event in session.run("Write a summary to output.txt."):
        match event:
            case act.ToolConfirmationRequired(tool_use_id=uid, tool_name=name, input=args):
                print(f"\n[requires_action] {name}({args})")
                print("  → confirm_tool()")
                await session.confirm_tool(uid)   # resume the blocked tool

            case act.SessionIdle(stop_reason=r):
                print(f"\n[idle: {r.type}]")
                if r.type == "end_turn":
                    break
                # requires_action: loop continues after confirm_tool resolves

            case act.AgentMessage(text=t, delta=True):
                print(t, end="", flush=True)

            case act.SessionRunning():
                print(f"\n[running]")


# ---------------------------------------------------------------------------
# Pattern C — Interrupt
# ---------------------------------------------------------------------------

async def run_with_interrupt():
    print("\n=== Pattern C: Interrupt mid-run ===")

    session = act.Session(fs_agent)

    async def consume():
        async for event in session.run("Read every file in the current directory."):
            match event:
                case act.AgentMessage(text=t, delta=True):
                    print(t, end="", flush=True)
                case act.SessionIdle(stop_reason=r):
                    print(f"\n[idle: {r.type}]")
                    break
                case act.SessionRunning():
                    print("[running]")

    task = asyncio.create_task(consume())
    await asyncio.sleep(1)

    print("\n  [user triggered interrupt]")
    session.interrupt()

    await task
    print(f"Status after interrupt: {session.status}")  # idle

    # Session is still usable — continue with a new turn
    async for event in session.run("Just read config.yaml instead."):
        match event:
            case act.AgentMessage(text=t, delta=True):
                print(t, end="", flush=True)
            case act.SessionIdle(stop_reason=r) if r.type == "end_turn":
                break


# ---------------------------------------------------------------------------
# Run all patterns
# ---------------------------------------------------------------------------

async def main():
    await run_with_callback()
    await run_with_events()
    await run_with_interrupt()


if __name__ == "__main__":
    asyncio.run(main())
