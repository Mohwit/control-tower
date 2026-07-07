"""Example 02 — Config-driven agent loaded from YAML.

The AgentConfig is the single source of truth. Swap YAML files to change
agent behaviour without touching implementation code.

YAML file: act/examples/agents/weather.yaml
"""

import asyncio
import pathlib

import act
from act import AgentConfig

AGENTS_DIR = pathlib.Path(__file__).parent / "agents"


def get_current_weather(city: str, unit: str = "celsius") -> dict:
    """Return current weather for a city."""
    return {"city": city, "temp": 22, "unit": unit, "condition": "sunny"}


def get_forecast(city: str, days: int = 3) -> list[dict]:
    """Return a multi-day forecast."""
    return [
        {"day": i + 1, "temp_high": 20 + i, "condition": "partly cloudy"}
        for i in range(days)
    ]


weather = act.Agent(
    config=AgentConfig.from_yaml(AGENTS_DIR / "weather.yaml"),
    tools=[get_current_weather, get_forecast],
)


async def main():
    print(f"Agent name from YAML: {weather._config.name}")
    print(f"Model:                {weather._config.model_id}")

    result = await weather.run("What's the weather in Paris today?")
    print(result.output)


if __name__ == "__main__":
    asyncio.run(main())
