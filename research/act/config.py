"""AgentConfig — pydantic spec for an ACT agent.

Mirrors the Anthropic managed-agents ``agents.create()`` payload so the same
config dict/YAML is portable between local ACT runs and a future hosted deployment.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolPermission(BaseModel):
    """Controls whether the agent executes a tool automatically or asks first."""
    type: Literal["auto", "always_ask"] = "auto"


class ToolConfig(BaseModel):
    """Config for a single tool entry in the agent spec."""
    name: str
    enabled: bool = True
    permission_policy: ToolPermission = Field(default_factory=ToolPermission)


class MCPServerConfig(BaseModel):
    """Config for an MCP server the agent can call."""
    name: str
    url: str
    transport: Literal["sse", "stdio", "streamable_http"] = "sse"
    env: dict[str, str] = Field(default_factory=dict)


class ModelConfig(BaseModel):
    """Model selection. Mirrors managed-agents ``{id, speed}`` object."""
    id: str = "claude-opus-4-8"
    speed: Literal["standard", "fast"] = "standard"
    settings: dict[str, Any] | None = None  # forwarded to pydantic_ai.ModelSettings


class MultiAgentConfig(BaseModel):
    """Coordinator declaration — mirrors managed-agents ``multiagent`` field."""
    type: Literal["coordinator"] = "coordinator"
    agents: list[str] = Field(default_factory=list)  # agent names in the roster


class SkillConfig(BaseModel):
    """Domain-specific context bundle (future; reserved for compatibility)."""
    name: str
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentConfig(BaseModel):
    """Full agent specification.

    The single source of truth for what an agent is. Pass inline or load from
    YAML/JSON. All fields mirror the managed-agents ``agents.create()`` payload.

    Inline usage::

        config = AgentConfig(
            name="weather-agent",
            model=ModelConfig(id="claude-opus-4-8"),
            system="You are a weather assistant.",
            tools=[ToolConfig(name="get_forecast")],
            retries=2,
        )

    YAML file (``agents/weather.yaml``)::

        name: weather-agent
        model:
          id: claude-opus-4-8
        system: You are a weather assistant.
        tools:
          - name: get_forecast
            permission_policy:
              type: auto
        retries: 2

    Load from file::

        config = AgentConfig.from_yaml("agents/weather.yaml")
        config = AgentConfig.from_json("agents/weather.json")
    """

    name: str
    model: ModelConfig | str = Field(default_factory=lambda: ModelConfig())
    system: str = ""
    description: str | None = None
    tools: list[ToolConfig] = Field(default_factory=list)
    mcp_servers: list[MCPServerConfig] = Field(default_factory=list)
    skills: list[SkillConfig] = Field(default_factory=list)
    multiagent: MultiAgentConfig | None = None
    retries: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def model_id(self) -> str:
        """Resolved model ID string for pydantic-ai."""
        return self.model.id if isinstance(self.model, ModelConfig) else self.model

    @property
    def model_settings(self) -> dict[str, Any] | None:
        """ModelSettings dict if provided, else None."""
        if isinstance(self.model, ModelConfig):
            return self.model.settings
        return None

    @classmethod
    def from_yaml(cls, path: str) -> "AgentConfig":
        """Load config from a YAML file. Requires ``pyyaml``."""
        import yaml  # optional dep
        with open(path) as f:
            return cls.model_validate(yaml.safe_load(f))

    @classmethod
    def from_json(cls, path: str) -> "AgentConfig":
        """Load config from a JSON file."""
        with open(path) as f:
            return cls.model_validate(json.load(f))
