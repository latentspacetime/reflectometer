"""How much of a prefix a provider is willing to cache.

Two published rules decide how many of the tokens before a break were cached
at all. A provider caches in whole blocks of a fixed size, so a prefix is
rounded down to that size, and a provider refuses to cache a prefix shorter
than a minimum. Set both to the numbers in your provider's documentation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CacheProfile:
    """Cache granularity and the shortest prefix a provider will cache."""

    name: str
    block_tokens: int = 1
    min_prefix_tokens: int = 0

    def __post_init__(self) -> None:
        if self.block_tokens < 1:
            raise ValueError("block_tokens must be at least 1")
        if self.min_prefix_tokens < 0:
            raise ValueError("min_prefix_tokens cannot be negative")

    def cacheable(self, tokens: int) -> int:
        """Tokens of a ``tokens``-long prefix that this provider would cache."""
        if tokens < self.min_prefix_tokens:
            return 0
        return (tokens // self.block_tokens) * self.block_tokens


EXACT = CacheProfile("exact")
"""Every shared token counts, which is the right reading when the rules are unknown."""

PROFILES: dict[str, CacheProfile] = {
    "exact": EXACT,
    "block-16": CacheProfile("block-16", block_tokens=16),
    "block-64": CacheProfile("block-64", block_tokens=64),
    "breakpoint-1024": CacheProfile("breakpoint-1024", min_prefix_tokens=1024),
    "breakpoint-2048": CacheProfile("breakpoint-2048", min_prefix_tokens=2048),
}
"""Profiles named after the rule they apply, so the name does not go stale."""


def profile(name: str) -> CacheProfile:
    try:
        return PROFILES[name]
    except KeyError:
        raise ValueError(f"unknown profile {name!r}; choose one of {sorted(PROFILES)}") from None
