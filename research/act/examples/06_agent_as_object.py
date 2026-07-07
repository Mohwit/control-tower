"""Example 06 — Factory pattern: build agents dynamically from YAML configs."""

import pathlib
import act
from act import Agent, AgentConfig

AGENTS_DIR = pathlib.Path(__file__).parent / "agents"


def load_agent(yaml_path: str | pathlib.Path, tools: list) -> act.Agent:
    """Load an agent from a YAML spec + a runtime tool list."""
    config = AgentConfig.from_yaml(yaml_path)
    return act.Agent(config=config, tools=tools)


# Plain callables — shared across agents loaded from different YAML files

def get_forecast(city: str, days: int = 1) -> dict:
    """Return a weather forecast."""
    return {"city": city, "days": days, "forecast": "Sunny, 22°C"}


def get_air_quality(city: str) -> dict:
    """Return the air quality index for a city."""
    return {"city": city, "aqi": 35, "category": "Good"}


weather = load_agent(AGENTS_DIR / "weather.yaml", tools=[get_forecast, get_air_quality])
print(weather)  # Agent(name='weather-agent', model='claude-opus-4-8')
