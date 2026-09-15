"""Find the edit that threw away your prompt cache, and the rewrite that gets it back."""

from __future__ import annotations

from .blocks import Block, Prompt, prompt_from_dicts
from .breaks import Break, Refusal, locate, shared_prefix_length, surviving_prefix
from .cost import Prices, cost_of
from .profiles import EXACT, PROFILES, CacheProfile, profile
from .repair import Move, Repair, plan, rebuild, volatile_blocks
from .report import BlockLine, Report, analyse
from .tokens import TokenCounter, count_tokens, estimate_tokens

__version__ = "0.1.0"

__all__ = [
    "EXACT",
    "PROFILES",
    "Block",
    "BlockLine",
    "Break",
    "CacheProfile",
    "Move",
    "Prices",
    "Prompt",
    "Refusal",
    "Repair",
    "Report",
    "TokenCounter",
    "__version__",
    "analyse",
    "cost_of",
    "count_tokens",
    "estimate_tokens",
    "locate",
    "plan",
    "profile",
    "prompt_from_dicts",
    "rebuild",
    "shared_prefix_length",
    "surviving_prefix",
    "volatile_blocks",
]
