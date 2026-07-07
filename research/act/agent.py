"""Agent — object-based ACT agent.

Mirrors ``client.beta.agents.create(...)`` from the managed-agents API.
Pass an ``AgentConfig`` spec and a list of tool callables — no class boilerplate.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent as _PydanticAgent

from act.config import AgentConfig


def _build_pai_kwargs(
    config: AgentConfig,
    tools: list,
    deps_type: type | None,
    output_type: type,
    capabilities: list | None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = dict(
        model=config.model_id,
        name=config.name,
        instructions=config.system or None,
        output_type=output_type,
        retries=config.retries,
        tools=tools,
    )
    if config.description:
        kwargs["description"] = config.description
    if config.model_settings:
        kwargs["model_settings"] = config.model_settings
    if deps_type is not None:
        kwargs["deps_type"] = deps_type
    if capabilities:
        kwargs["capabilities"] = capabilities
    return kwargs


class Agent:
    """An ACT agent — config-driven, object-based.

    Mirrors ``client.beta.agents.create(...)`` from the managed-agents API.
    Tools are plain callables (sync or async) passed via the ``tools`` list.

    Parameters
    ----------
    config:
        ``AgentConfig`` pydantic model — name, model, system prompt, retries, etc.
        Load from YAML/JSON or construct inline.
    tools:
        List of callable tool functions. Functions may optionally take
        ``ctx: RunContext[DepsT]`` as their first argument for dependency injection.
    deps_type:
        Optional dependency injection type.
    output_type:
        Expected output type; defaults to ``str``.
    capabilities:
        List of ``ACTCapability`` instances for harness cross-cutting concerns.

    Usage::

        def get_forecast(city: str) -> str:
            return f"Sunny in {city}."

        weather = act.Agent(
            config=AgentConfig(
                name="weather-agent",
                model="claude-opus-4-8",
                system="You are a weather assistant.",
            ),
            tools=[get_forecast],
        )

        result = await weather.run("What's the weather in NYC?")
        print(result.output)

    From YAML::

        weather = act.Agent(
            config=AgentConfig.from_yaml("agents/weather.yaml"),
            tools=[get_forecast],
        )

    With session::

        session = act.Session(weather)
        async for event in session.run("What's the weather in Paris?"):
            ...

    With coordinator::

        @act.coordinator(config=coordinator_cfg, agents=[weather, calendar])
        class Planner:
            pass
    """

    def __init__(
        self,
        config: AgentConfig,
        *,
        tools: list | None = None,
        deps_type: type | None = None,
        output_type: type = str,
        capabilities: list | None = None,
    ) -> None:
        self._config = config
        self._tools: list = tools or []
        self._deps_type = deps_type
        self._output_type = output_type
        self._capabilities = capabilities
        self._pai_agent = _PydanticAgent(
            **_build_pai_kwargs(config, self._tools, deps_type, output_type, capabilities)
        )

    async def run(self, user_prompt: str, *, deps: Any = None, **kwargs):
        """One-shot stateless run. Returns ``AgentRunResult``."""
        return await self._pai_agent.run(user_prompt, deps=deps, **kwargs)

    def run_sync(self, user_prompt: str, *, deps: Any = None, **kwargs):
        """Synchronous one-shot run."""
        return self._pai_agent.run_sync(user_prompt, deps=deps, **kwargs)

    def run_stream(self, user_prompt: str, *, deps: Any = None, **kwargs):
        """Raw pydantic-ai stream context manager. Prefer ``act.Session`` for the event API."""
        return self._pai_agent.run_stream(user_prompt, deps=deps, **kwargs)

    def __repr__(self) -> str:
        return f"Agent(name={self._config.name!r}, model={self._config.model_id!r})"
