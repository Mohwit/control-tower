"""Example 01 — Basic agent: inline config, tools, one-shot run."""

import asyncio
import act
from act import Agent, AgentConfig, ModelConfig


def add(x: float, y: float) -> float:
    """Add two numbers."""
    return x + y


def multiply(x: float, y: float) -> float:
    """Multiply two numbers."""
    return x * y


def divide(x: float, y: float) -> float:
    """Divide x by y. Raises ValueError if y is zero."""
    if y == 0:
        raise ValueError("Division by zero")
    return x / y


calculator = act.Agent(
    config=AgentConfig(
        name="calculator",
        model=ModelConfig(id="claude-opus-4-8"),
        system="You are a precise calculator assistant. Use the provided tools.",
        description="Performs arithmetic calculations.",
        retries=2,
    ),
    tools=[add, multiply, divide],
)


async def main():
    result = await calculator.run("What is (15 + 27) * 3?")
    print(result.output)
    print(f"tokens used: {result.usage().total_tokens}")


if __name__ == "__main__":
    asyncio.run(main())
