"""Session — full-lifecycle stateful conversation thread.

Mirrors the managed-agents sessions model end-to-end:

Status machine::

    CREATE
      │
      ▼
    idle ◄──── user.message / confirm_tool / deny_tool
      │
      ▼
    running ──► session.status_running
      │
      ├── transient error ──► rescheduling ──► (auto retry) ──► running
      │
      ├── requires_action ──► idle (stop_reason=requires_action)
      │                            │
      │                            └── confirm_tool / deny_tool ──► running
      │
      ├── end_turn ──► idle (stop_reason=end_turn)
      │
      ├── interrupt() ──► idle (stop_reason=interrupted)
      │
      └── fatal error ──► terminated  (permanent)

    idle / terminated ──► archive() ──► archived  (history preserved)
    idle / terminated / archived ──► delete() ──► cleared

Managed-agents mapping
----------------------
``sessions.create(agent)``           → ``Session(agent)``
``sessions.events.stream(id)``       → ``async for event in session.run(input)``
``sessions.events.send(interrupt)``  → ``session.interrupt()``
``session.status == idle(requires_action)`` → ``ToolConfirmationRequired`` event
``user.tool_confirmation allow``     → ``session.confirm_tool(tool_use_id)``
``user.tool_confirmation deny``      → ``session.deny_tool(tool_use_id)``
``POST /v1/sessions/:id``            → ``session.update_tools(tools)``
``POST /v1/sessions/:id/archive``    → ``session.archive()``
``DELETE /v1/sessions/:id``          → ``session.delete()``
history persists server-side         → ``session.save()`` / ``Session.load()``
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import uuid
from collections.abc import AsyncGenerator
from typing import Any, Callable

from pydantic_ai import Agent as _PydanticAgent
from pydantic_ai.messages import ModelMessagesTypeAdapter

from act.agent import _build_pai_kwargs
from act.harness.capability import ACTCapability
from act.events import (
    AgentMessage,
    Event,
    SessionError,
    SessionIdle,
    SessionRescheduling,
    SessionRunning,
    SessionTerminated,
    StopReason,
    ToolConfirmationRequired,
    UsageUpdate,
)
from act.session_status import SessionStatus, UsageStats


# Sentinel placed in the event queue when the worker task exits
_DONE = object()


class SessionArchivedError(RuntimeError):
    """Raised when trying to run or clear an archived session."""


class SessionTerminatedError(RuntimeError):
    """Raised when trying to run a permanently terminated session."""


def _is_transient(exc: Exception) -> bool:
    """Heuristic: is this error worth retrying?"""
    transient_bases = (ConnectionError, TimeoutError, OSError)
    keywords = ("timeout", "connection", "503", "429", "rate limit", "overloaded")
    return isinstance(exc, transient_bases) or any(k in str(exc).lower() for k in keywords)


class Session:
    """Stateful conversation thread with full managed-agents lifecycle.

    Parameters
    ----------
    agent:
        An ``act.Agent`` instance.
    session_id:
        Optional stable identifier. A UUID is generated if omitted.
    on_tool_confirmation:
        Callback invoked for tools with ``always_ask`` permission policy.
        Signature: ``(tool_name: str, args: dict) -> bool`` (sync or async).
        Return ``True`` to allow, ``False`` to deny.
        If omitted, tools with ``always_ask`` emit ``ToolConfirmationRequired``
        and pause until ``session.confirm_tool()`` or ``session.deny_tool()``
        is called from the consuming async-for loop.
    max_retries:
        Maximum automatic retry attempts on transient errors (rescheduling).
        Default 2.

    Usage — basic::

        session = act.Session(weather)

        async for event in session.run("What's the weather in Tokyo?"):
            match event:
                case act.AgentMessage(text=t, delta=True):
                    print(t, end="", flush=True)
                case act.SessionIdle(stop_reason=r) if r.type == "end_turn":
                    print()
                case act.SessionTerminated(error=e):
                    print(f"Fatal: {e}")

    Usage — tool confirmation (callback style)::

        session = act.Session(
            agent,
            on_tool_confirmation=lambda tool_name, args: tool_name != "rm_rf",
        )

    Usage — tool confirmation (event-driven, requires_action style)::

        session = act.Session(agent)   # no callback — events pause the loop

        async for event in session.run(user_input):
            match event:
                case act.ToolConfirmationRequired(tool_use_id=uid, tool_name=name):
                    if await ask_user(f"Allow {name}?"):
                        await session.confirm_tool(uid)
                    else:
                        await session.deny_tool(uid)
                case act.SessionIdle(stop_reason=r) if r.type == "end_turn":
                    break

    Usage — interrupt mid-run::

        task = asyncio.create_task(consume_events(session.run("Write a novel")))
        await asyncio.sleep(5)
        session.interrupt()
        await task

    Usage — multi-turn::

        async for event in session.run("Tell me about Paris"):
            ...

        async for event in session.run("And what about Berlin?"):
            # Full conversation history is forwarded automatically
            ...

    Usage — persistence::

        blob = session.save()
        restored = act.Session.load(agent, blob, session_id=session.session_id)
    """

    def __init__(
        self,
        agent,
        *,
        session_id: str | None = None,
        on_tool_confirmation: Callable | None = None,
        max_retries: int = 2,
        capabilities: list[ACTCapability] | None = None,
    ) -> None:
        self._agent = agent
        self._history: list = []
        self.session_id: str = session_id or str(uuid.uuid4())
        self._on_tool_confirmation = on_tool_confirmation
        self._max_retries = max_retries
        self._capabilities: list[ACTCapability] = capabilities or []

        self._status: SessionStatus = SessionStatus.IDLE
        self._usage: UsageStats = UsageStats()
        self._interrupt_event: asyncio.Event = asyncio.Event()
        self._current_task: asyncio.Task | None = None
        self._event_queue: asyncio.Queue | None = None

        # Pending tool confirmations: tool_use_id → asyncio.Future[bool]
        self._pending_confirmations: dict[str, asyncio.Future] = {}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def status(self) -> SessionStatus:
        """Current session status. Mirrors managed-agents status field."""
        return self._status

    @property
    def usage(self) -> UsageStats:
        """Cumulative token usage across all turns in this session."""
        return self._usage

    @property
    def history(self) -> list:
        """Read-only view of the conversation message history."""
        return list(self._history)

    # ------------------------------------------------------------------
    # Core run
    # ------------------------------------------------------------------

    async def run(
        self,
        user_input: str,
        *,
        deps: Any = None,
        interrupt_current: bool = False,
    ) -> AsyncGenerator[Event, None]:
        """Execute one conversation turn and yield events.

        Re-entrant: call repeatedly for multi-turn conversations. History is
        carried forward automatically.

        Yields (in order):
            ``SessionRunning``
            ``AgentMessage(delta=True)`` × N
            [``ToolConfirmationRequired`` + ``SessionIdle(requires_action)``] × M
            [``SessionRescheduling``] × K (auto-retry on transient errors)
            ``SessionIdle(end_turn)``  OR  ``SessionTerminated``

        Parameters
        ----------
        user_input:
            The user's message for this turn.
        deps:
            Dependency injection value forwarded to pydantic-ai tools.
        interrupt_current:
            If True, interrupt any in-progress run before starting this one.
        """
        if self._status == SessionStatus.ARCHIVED:
            raise SessionArchivedError("Cannot run on an archived session.")
        if self._status == SessionStatus.TERMINATED:
            raise SessionTerminatedError("Session is permanently terminated.")
        if interrupt_current:
            self.interrupt()

        # Session-level capability hooks — run before_turn in order
        for cap in self._capabilities:
            user_input = await cap.before_turn(self, user_input)

        self._interrupt_event.clear()
        self._status = SessionStatus.RUNNING
        event_queue: asyncio.Queue = asyncio.Queue()
        self._event_queue = event_queue

        effective_pai = self._build_effective_agent(event_queue)
        session_ref = self

        async def worker():
            retries = 0
            while True:
                try:
                    async with effective_pai.run_stream(
                        user_input,
                        message_history=session_ref._history or None,
                        deps=deps,
                    ) as streamed:
                        async for chunk in streamed.stream_text(delta=True):
                            if session_ref._interrupt_event.is_set():
                                await event_queue.put(SessionIdle(
                                    stop_reason=StopReason(type="interrupted"),
                                ))
                                return
                            if chunk:
                                await event_queue.put(AgentMessage(text=chunk, delta=True))

                        session_ref._history = streamed.all_messages()
                        run_usage = streamed.usage()
                        session_ref._usage.accumulate(run_usage)

                        usage_dict: dict[str, Any] | None = None
                        if run_usage is not None:
                            usage_dict = {
                                "input_tokens": getattr(run_usage, "request_tokens", 0) or 0,
                                "output_tokens": getattr(run_usage, "response_tokens", 0) or 0,
                                "total_tokens": getattr(run_usage, "total_tokens", 0) or 0,
                            }
                            await event_queue.put(UsageUpdate(
                                input_tokens=usage_dict["input_tokens"],
                                output_tokens=usage_dict["output_tokens"],
                                total_tokens=usage_dict["total_tokens"],
                            ))

                        await event_queue.put(SessionIdle(
                            stop_reason=StopReason(type="end_turn"),
                            usage=usage_dict,
                        ))
                        return

                except asyncio.CancelledError:
                    await event_queue.put(SessionIdle(
                        stop_reason=StopReason(type="interrupted"),
                    ))
                    return

                except Exception as exc:
                    if retries < session_ref._max_retries and _is_transient(exc):
                        retries += 1
                        await event_queue.put(SessionRescheduling(
                            error=str(exc),
                            attempt=retries,
                        ))
                        await asyncio.sleep(min(2 ** retries, 30))
                        continue
                    else:
                        await event_queue.put(SessionError(
                            message=str(exc),
                            retry_status="non_retryable",
                        ))
                        await event_queue.put(SessionTerminated(error=str(exc)))
                        return

                # end while
            # end async def worker

        task = asyncio.create_task(worker())
        self._current_task = task

        try:
            yield SessionRunning()

            while True:
                event = await event_queue.get()
                if event is _DONE:
                    break

                # Track status from emitted events
                if isinstance(event, SessionIdle):
                    self._status = SessionStatus.IDLE
                elif isinstance(event, SessionRescheduling):
                    self._status = SessionStatus.RESCHEDULING
                elif isinstance(event, SessionTerminated):
                    self._status = SessionStatus.TERMINATED

                yield event

                # Break conditions
                if isinstance(event, SessionIdle):
                    if event.stop_reason.type == "end_turn":
                        for cap in self._capabilities:
                            await cap.after_turn(self)
                        break
                    if event.stop_reason.type == "interrupted":
                        break
                    # requires_action → keep the loop alive; worker is blocked
                    # until confirm_tool/deny_tool resolves the pending future
                elif isinstance(event, SessionTerminated):
                    break

        finally:
            self._event_queue = None
            self._current_task = None
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

    # ------------------------------------------------------------------
    # Interrupt
    # ------------------------------------------------------------------

    def interrupt(self) -> None:
        """Signal the current run to stop at the next stream chunk.

        The run() generator yields ``SessionIdle(interrupted)`` and returns.
        The session returns to ``idle``; history up to the interrupt is preserved.
        On the next ``run()`` call the conversation continues from there.
        """
        self._interrupt_event.set()
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()

    # ------------------------------------------------------------------
    # Tool confirmation — respond to requires_action
    # ------------------------------------------------------------------

    async def confirm_tool(self, tool_use_id: str) -> None:
        """Allow a pending tool call that was paused for confirmation.

        Call in response to a ``ToolConfirmationRequired`` event.
        Mirrors ``user.tool_confirmation {result: "allow"}``.
        """
        fut = self._pending_confirmations.get(tool_use_id)
        if fut and not fut.done():
            fut.set_result(True)

    async def deny_tool(
        self,
        tool_use_id: str,
        *,
        deny_message: str | None = None,
    ) -> None:
        """Deny a pending tool call that was paused for confirmation.

        Call in response to a ``ToolConfirmationRequired`` event.
        Mirrors ``user.tool_confirmation {result: "deny"}``.
        The agent receives ``"Tool '<name>' was denied."`` as the tool result.
        """
        fut = self._pending_confirmations.get(tool_use_id)
        if fut and not fut.done():
            fut.set_result(False)

    # ------------------------------------------------------------------
    # Session operations
    # ------------------------------------------------------------------

    def archive(self) -> None:
        """Prevent new events while preserving history.

        Mirrors ``POST /v1/sessions/:id/archive``.
        Raises ``RuntimeError`` if the session is currently running.
        """
        if self._status == SessionStatus.RUNNING:
            raise RuntimeError(
                "Cannot archive a running session. Call interrupt() first."
            )
        self._status = SessionStatus.ARCHIVED

    def delete(self) -> None:
        """Clear history and mark the session deleted.

        Mirrors ``DELETE /v1/sessions/:id``.
        Raises ``RuntimeError`` if the session is currently running.
        """
        if self._status == SessionStatus.RUNNING:
            raise RuntimeError(
                "Cannot delete a running session. Call interrupt() first."
            )
        self._history = []
        self._pending_confirmations.clear()
        self._status = SessionStatus.TERMINATED

    def update_tools(self, tools: list) -> None:
        """Replace the agent's tool list for this session (idle-only).

        Mirrors ``POST /v1/sessions/:id`` tool update. Full replacement —
        the provided list replaces the existing tools entirely. Updates are
        session-local and do NOT affect other sessions using the same agent.

        Raises ``RuntimeError`` if the session is not idle.
        """
        if self._status != SessionStatus.IDLE:
            raise RuntimeError(
                f"Can only update tools when idle (current status: {self._status.value})."
            )
        self._agent._tools = tools
        self._agent._pai_agent = _PydanticAgent(
            **_build_pai_kwargs(
                self._agent._config,
                tools,
                self._agent._deps_type,
                self._agent._output_type,
                self._agent._capabilities,
            )
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> bytes:
        """Serialize conversation history to JSON bytes.

        Store the bytes anywhere (database, Redis, file) and restore with
        ``Session.load()`` to resume the conversation in a new process.
        """
        return ModelMessagesTypeAdapter.dump_json(self._history)

    @classmethod
    def load(
        cls,
        agent,
        data: bytes,
        *,
        session_id: str | None = None,
        on_tool_confirmation: Callable | None = None,
        max_retries: int = 2,
    ) -> "Session":
        """Restore a session from bytes produced by ``save()``."""
        session = cls(
            agent,
            session_id=session_id,
            on_tool_confirmation=on_tool_confirmation,
            max_retries=max_retries,
        )
        session._history = ModelMessagesTypeAdapter.validate_json(data)
        return session

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Reset conversation history. Keeps session_id and status."""
        if self._status == SessionStatus.ARCHIVED:
            raise SessionArchivedError("Cannot clear an archived session.")
        self._history = []

    @property
    def turn_count(self) -> int:
        """Number of completed turns (model responses) in this session."""
        return sum(
            1 for m in self._history
            if hasattr(m, "parts") and any(
                getattr(p, "part_kind", None) == "text" for p in m.parts
            )
        )

    def __repr__(self) -> str:
        return (
            f"Session(id={self.session_id!r}, "
            f"status={self._status.value!r}, "
            f"turns={self.turn_count})"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _has_confirmation_tools(self) -> bool:
        """True if any configured tool has always_ask permission policy."""
        return any(
            tc.permission_policy.type == "always_ask"
            for tc in self._agent._config.tools
        )

    def _build_effective_agent(self, event_queue: asyncio.Queue):
        """Return a pydantic-ai agent for this run.

        If there are always_ask tools, returns a new agent with confirmation
        wrappers around those tools. Otherwise returns _pai_agent unchanged.
        """
        if not self._has_confirmation_tools():
            return self._agent._pai_agent

        policy_map = {tc.name: tc.permission_policy.type for tc in self._agent._config.tools}
        wrapped = []
        for fn in self._agent._tools:
            name = fn.__name__
            if policy_map.get(name) == "always_ask":
                wrapped.append(self._make_confirmation_wrapper(fn, name, event_queue))
            else:
                wrapped.append(fn)

        return _PydanticAgent(
            **_build_pai_kwargs(
                self._agent._config,
                wrapped,
                self._agent._deps_type,
                self._agent._output_type,
                self._agent._capabilities,
            )
        )

    def _make_confirmation_wrapper(self, fn, tool_name: str, event_queue: asyncio.Queue):
        """Wrap a tool function with a confirmation gate.

        If ``on_tool_confirmation`` callback is set: call it for allow/deny.
        Otherwise: emit events and await ``confirm_tool``/``deny_tool``.
        """
        is_async = inspect.iscoroutinefunction(fn)
        orig_sig = inspect.signature(fn)
        callback = self._on_tool_confirmation
        pending = self._pending_confirmations

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            if callback is not None:
                # Callback-based: call it synchronously (or await if async)
                result = callback(tool_name, kwargs)
                if inspect.isawaitable(result):
                    result = await result
                if not result:
                    return f"Tool '{tool_name}' execution was denied."
            else:
                # Event-driven: pause the stream and wait for explicit confirm/deny
                tool_use_id = str(uuid.uuid4())
                fut: asyncio.Future = asyncio.get_event_loop().create_future()
                pending[tool_use_id] = fut

                await event_queue.put(ToolConfirmationRequired(
                    tool_use_id=tool_use_id,
                    tool_name=tool_name,
                    input=kwargs,
                ))
                await event_queue.put(SessionIdle(
                    stop_reason=StopReason(
                        type="requires_action",
                        event_ids=[tool_use_id],
                    ),
                ))

                allowed = await fut
                pending.pop(tool_use_id, None)

                if not allowed:
                    return f"Tool '{tool_name}' execution was denied."

            if is_async:
                return await fn(*args, **kwargs)
            return fn(*args, **kwargs)

        wrapper.__signature__ = orig_sig
        return wrapper
