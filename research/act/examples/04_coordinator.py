"""Example 04 — Multi-agent coordinator.

Mirrors managed-agents multiagent: {type: coordinator, agents: [...]}.
The coordinator's LLM decides which sub-agent to delegate to.

Architecture:
    PlanningCoordinator
    ├── weather    (get current weather)
    ├── calendar   (find available slots)
    └── search     (web search)
"""

import asyncio
import act
from act import AgentConfig, ModelConfig


# --- Sub-agents ---

def get_weather(city: str) -> str:
    return f"Sunny, 22°C in {city}."


weather = act.Agent(
    config=AgentConfig(
        name="weather-agent",
        model=ModelConfig(id="claude-opus-4-8"),
        system="You answer weather questions.",
        description="Provides weather information for any city.",
    ),
    tools=[get_weather],
)


def find_slots(date: str, duration_minutes: int = 60) -> list[str]:
    """Find available time slots on a given date."""
    return ["09:00", "14:00", "16:30"]


def book_slot(date: str, time: str, title: str) -> str:
    return f"Booked '{title}' on {date} at {time}."


calendar = act.Agent(
    config=AgentConfig(
        name="calendar-agent",
        model=ModelConfig(id="claude-opus-4-8"),
        system="You help schedule meetings and find available times.",
        description="Manages calendar scheduling and availability.",
    ),
    tools=[find_slots, book_slot],
)


def search(query: str) -> str:
    return f"Top result for '{query}': [mock search result]"


search_agent = act.Agent(
    config=AgentConfig(
        name="search-agent",
        model=ModelConfig(id="claude-opus-4-8"),
        system="You research topics and return concise summaries.",
        description="Searches the web and summarises results.",
    ),
    tools=[search],
)


# --- Coordinator ---

@act.coordinator(
    config=AgentConfig(
        name="planning-coordinator",
        model=ModelConfig(id="claude-opus-4-8"),
        system=(
            "You are a planning coordinator. For each user request, delegate to "
            "the most appropriate specialist agent. If the task needs multiple "
            "agents, coordinate them and combine their results into a single answer."
        ),
        description="Routes planning tasks to weather, calendar, and search agents.",
    ),
    agents=[weather, calendar, search_agent],
)
class PlanningCoordinator:
    pass


async def main():
    result = await PlanningCoordinator.run(
        "It's sunny in Paris next Tuesday. Book a 2-hour lunch meeting for me that day."
    )
    print(result.output)

    session = act.Session(PlanningCoordinator)
    async for event in session.run("What agents do you have available?"):
        if isinstance(event, act.AgentMessage):
            print(event.text, end="", flush=True)
        elif isinstance(event, act.SessionIdle) and event.stop_reason.type == "end_turn":
            print()
            break


if __name__ == "__main__":
    asyncio.run(main())
