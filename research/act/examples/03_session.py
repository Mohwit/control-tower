"""Example 03 — Stateful session with full lifecycle event stream.

Covers:
- Multi-turn conversation with automatic history
- All session status transitions (idle / running / terminated)
- Interrupt mid-run
- Usage tracking
- save / load persistence
"""

import asyncio
import act
from act import AgentConfig, ModelConfig, SessionStatus


def get_weather(city: str) -> str:
    return f"Sunny and 24°C in {city}."


def get_flight_price(origin: str, destination: str) -> str:
    return f"Flights from {origin} to {destination}: from $350."


travel = act.Agent(
    config=AgentConfig(
        name="travel-assistant",
        model=ModelConfig(id="claude-opus-4-8"),
        system="You are a helpful travel assistant with memory of the conversation.",
    ),
    tools=[get_weather, get_flight_price],
)


async def stream_turn(session: act.Session, user_input: str) -> None:
    print(f"\nUser: {user_input}")
    print("Agent: ", end="", flush=True)

    async for event in session.run(user_input):
        match event:
            case act.AgentMessage(text=chunk, delta=True):
                print(chunk, end="", flush=True)
            case act.SessionIdle(stop_reason=r, usage=u):
                if r.type == "end_turn":
                    tokens = u.get("total_tokens") if u else "?"
                    print(f"\n[end_turn | tokens: {tokens}]")
            case act.SessionRescheduling(error=e, attempt=n):
                print(f"\n[retrying attempt {n}: {e}]")
            case act.SessionTerminated(error=e):
                print(f"\n[terminated: {e}]")
                break
            case act.SessionRunning():
                pass


async def main():
    session = act.Session(travel)
    print(f"Initial status: {session.status}")   # SessionStatus.IDLE

    # Multi-turn conversation
    await stream_turn(session, "I want to visit Tokyo. What's the weather like?")
    await stream_turn(session, "How much would flights from London cost?")
    await stream_turn(session, "Based on what you've told me, should I go in June?")

    print(f"\nTotal usage: {session.usage.to_dict()}")
    print(f"Turn count:  {session.turn_count}")

    # --- Persistence ---
    blob = session.save()
    print(f"\nSerialized: {len(blob)} bytes, id={session.session_id}")

    restored = act.Session.load(travel, blob, session_id=session.session_id)
    print(f"Restored {len(restored.history)} messages")
    await stream_turn(restored, "What was the flight price you mentioned?")

    # --- Session operations ---
    session.archive()
    print(f"\nArchived status: {session.status}")  # SessionStatus.ARCHIVED


if __name__ == "__main__":
    asyncio.run(main())
