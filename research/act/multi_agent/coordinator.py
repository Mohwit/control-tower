"""Coordinator agent — multi-agent orchestration.

Mirrors the managed-agents ``multiagent: {type: coordinator, agents: [...]}``
pattern. The coordinator is itself a pydantic-ai Agent whose tools are the
registered sub-agents. The LLM decides which sub-agent to delegate to, passes
it a query, and gets back the result.

Each sub-agent runs in isolation with its own context — mirroring managed-agents'
independent session threads per sub-agent.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent as _PydanticAgent

from act.config import AgentConfig


def _make_delegate_tool(sub_agent):
    cfg: AgentConfig = sub_agent._config
    fn_name = f"delegate_to_{cfg.name.replace('-', '_').replace(' ', '_')}"
    doc = cfg.description or f"Delegate a task to the {cfg.name} agent."

    async def delegate(query: str) -> str:
        result = await sub_agent._pai_agent.run(query)
        return str(result.output)

    delegate.__name__ = fn_name
    delegate.__doc__ = doc
    return delegate


def coordinator(
    config: AgentConfig,
    *,
    agents: list,
    deps_type: type | None = None,
    capabilities: list | None = None,
):
    """Class decorator for multi-agent coordinator.

    The coordinator is an agent whose only tools are delegation calls to the
    registered sub-agents.

    Parameters
    ----------
    config:
        ``AgentConfig`` for the coordinator itself (name, model, system prompt).
    agents:
        Ordered list of ``act.Agent`` instances the coordinator can delegate to.
        Max 20 (mirrors managed-agents limit).
    deps_type:
        Dependency injection type, propagated to pydantic-ai.
    capabilities:
        Harness capabilities (``ACTCapability`` instances).

    Usage::

        weather = act.Agent(config=AgentConfig(name="weather-agent", ...), tools=[get_weather])
        calendar = act.Agent(config=AgentConfig(name="calendar-agent", ...), tools=[find_slots])

        @act.coordinator(
            config=AgentConfig(
                name="planning-coordinator",
                model="claude-opus-4-8",
                system="Route each user request to the most appropriate specialist agent.",
            ),
            agents=[weather, calendar],
        )
        class PlanningCoordinator:
            pass

        result = await PlanningCoordinator.run("Book me a meeting if it'll be sunny Tuesday.")

        session = act.Session(PlanningCoordinator)
        async for event in session.run("Plan my week."):
            ...

    Sub-agent isolation
    -------------------
    Each ``delegate_to_*`` call is an independent ``agent.run()`` — no shared
    RunContext, no shared history. If you need to pass context inject it via
    the query string or extend this pattern to pass ``deps`` through.
    """

    if len(agents) > 20:
        raise ValueError(
            f"coordinator: got {len(agents)} agents; managed-agents limit is 20."
        )

    def decorator(cls):
        delegate_tools = [_make_delegate_tool(a) for a in agents]

        pai_kwargs: dict[str, Any] = dict(
            model=config.model_id,
            name=config.name,
            instructions=config.system or None,
            retries=config.retries,
            tools=delegate_tools,
        )
        if config.description:
            pai_kwargs["description"] = config.description
        if deps_type is not None:
            pai_kwargs["deps_type"] = deps_type
        if capabilities:
            pai_kwargs["capabilities"] = capabilities

        pai_agent = _PydanticAgent(**pai_kwargs)
        cls._config = config
        cls._agents = agents
        cls._pai_agent = pai_agent

        @classmethod
        async def run(klass, user_prompt: str, *, deps: Any = None, **kwargs):
            return await klass._pai_agent.run(user_prompt, deps=deps, **kwargs)

        @classmethod
        def run_sync(klass, user_prompt: str, *, deps: Any = None, **kwargs):
            return klass._pai_agent.run_sync(user_prompt, deps=deps, **kwargs)

        @classmethod
        def run_stream(klass, user_prompt: str, *, deps: Any = None, **kwargs):
            return klass._pai_agent.run_stream(user_prompt, deps=deps, **kwargs)

        cls.run = run
        cls.run_sync = run_sync
        cls.run_stream = run_stream

        return cls

    return decorator
