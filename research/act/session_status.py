"""Session status and cumulative usage tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SessionStatus(str, Enum):
    """Mirrors managed-agents session status values."""
    IDLE = "idle"
    RUNNING = "running"
    RESCHEDULING = "rescheduling"
    TERMINATED = "terminated"
    ARCHIVED = "archived"


@dataclass
class UsageStats:
    """Cumulative token usage across all turns in a session."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    def accumulate(self, usage) -> None:
        """Add pydantic-ai Usage object into running totals."""
        if usage is None:
            return
        # pydantic-ai Usage: request_tokens, response_tokens, total_tokens
        self.input_tokens += getattr(usage, "request_tokens", 0) or 0
        self.output_tokens += getattr(usage, "response_tokens", 0) or 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "total_tokens": self.total_tokens,
        }
