"""What a break costs.

A cached token is billed at the cache read rate and an uncached one at the
input rate, so every token the break threw away costs the difference between
the two, once per call that sends the prompt.
"""

from __future__ import annotations

from dataclasses import dataclass

PER_MILLION = 1_000_000


@dataclass(frozen=True)
class Prices:
    """Your provider's rates, both in dollars per million input tokens."""

    input_per_million: float
    cache_read_per_million: float

    def __post_init__(self) -> None:
        if self.input_per_million < 0 or self.cache_read_per_million < 0:
            raise ValueError("prices cannot be negative")
        if self.cache_read_per_million > self.input_per_million:
            raise ValueError("a cache read that costs more than an input token is not a cache")

    @property
    def saving_per_million(self) -> float:
        """Dollars a million cached tokens save against sending them uncached."""
        return self.input_per_million - self.cache_read_per_million


def cost_of(lost_tokens: int, prices: Prices, calls: int = 1) -> float:
    """Dollars that ``lost_tokens`` cost over ``calls`` calls."""
    if lost_tokens < 0:
        raise ValueError("lost_tokens cannot be negative")
    if calls < 0:
        raise ValueError("calls cannot be negative")
    return lost_tokens * calls * prices.saving_per_million / PER_MILLION
