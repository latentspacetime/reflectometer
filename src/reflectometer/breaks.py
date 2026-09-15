"""Locate the edit that broke the cache.

A prefix cache survives up to the first character where the new prompt stops
matching the old one. Everything the provider had cached past that point is
thrown away and billed again. This module finds that character, names the
block that holds it, and counts what it cost.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

from .blocks import Prompt
from .profiles import EXACT, CacheProfile
from .tokens import TokenCounter, count_tokens

Kind = Literal["edited", "inserted", "removed", "reordered"]

REFUSALS = {
    "identical": "the two prompts are the same, so no cache was broken",
    "nothing_shared": "the prompts differ at the first character, so no prefix was ever shared",
    "below_minimum_prefix": (
        "the original prompt is shorter than the shortest prefix this profile caches, "
        "so there was no cache to break"
    ),
}


@dataclass(frozen=True)
class Refusal:
    """A case where no break can be located, and why."""

    reason: str
    detail: str

    def to_dict(self) -> dict:
        return {"refused": self.reason, "because": self.detail}


@dataclass(frozen=True)
class Break:
    """Where the cache stopped surviving, and how much that threw away."""

    block_index: int
    block_name: str
    kind: Kind
    char_offset: int
    offset_in_block: int
    shared_tokens: int
    cached_before: int
    cached_after: int
    counted_exactly: bool

    @property
    def lost_tokens(self) -> int:
        """Cached tokens the provider discarded because of this break."""
        return self.cached_before - self.cached_after

    @property
    def survived(self) -> bool:
        return self.lost_tokens == 0

    def to_dict(self) -> dict:
        return {
            "block_index": self.block_index,
            "block_name": self.block_name,
            "kind": self.kind,
            "char_offset": self.char_offset,
            "offset_in_block": self.offset_in_block,
            "shared_tokens": self.shared_tokens,
            "cached_before": self.cached_before,
            "cached_after": self.cached_after,
            "lost_tokens": self.lost_tokens,
            "counted_exactly": self.counted_exactly,
        }


def shared_prefix_length(left: str, right: str) -> int:
    """Number of leading characters the two strings agree on."""
    limit = min(len(left), len(right))
    low, high = 0, limit
    if left[:limit] == right[:limit]:
        return limit
    while low < high:
        middle = (low + high + 1) // 2
        if left[:middle] == right[:middle]:
            low = middle
        else:
            high = middle - 1
    return low


def classify(cached: Prompt, sent: Prompt, block_index: int) -> Kind:
    """Name the edit that produced the break at ``block_index`` of the cached prompt.

    The block names of the two prompts are aligned, and the alignment says
    whether the block was edited in place, whether blocks were added or
    dropped ahead of it, or whether the same blocks came back in a new order.
    """
    old_names, new_names = list(cached.names()), list(sent.names())
    if old_names == new_names:
        return "edited"
    if sorted(old_names) == sorted(new_names):
        return "reordered"
    matcher = SequenceMatcher(a=old_names, b=new_names, autojunk=False)
    for tag, i1, _i2, _j1, _j2 in matcher.get_opcodes():
        if tag == "equal" or i1 > block_index:
            continue
        if tag == "insert":
            return "inserted"
        if tag == "delete":
            return "removed"
        return "inserted" if len(new_names) > len(old_names) else "removed"
    return "edited"


def locate(
    cached: Prompt,
    sent: Prompt,
    *,
    profile: CacheProfile = EXACT,
    counter: TokenCounter | None = None,
) -> Break | Refusal:
    """Find the first edit in ``sent`` that invalidates the cache built by ``cached``.

    Returns a ``Break`` describing the edit, or a ``Refusal`` when there is no
    break to report.
    """
    old_text, new_text = cached.text, sent.text
    if old_text == new_text:
        return Refusal("identical", REFUSALS["identical"])

    total_tokens = count_tokens(old_text, counter)
    cached_before = profile.cacheable(total_tokens)
    if cached_before == 0:
        return Refusal(
            "below_minimum_prefix",
            f"{REFUSALS['below_minimum_prefix']}: {total_tokens:,} tokens against a "
            f"minimum of {profile.min_prefix_tokens:,}",
        )

    offset = shared_prefix_length(old_text, new_text)
    if offset == 0:
        return Refusal("nothing_shared", REFUSALS["nothing_shared"])

    shared_tokens = count_tokens(old_text[:offset], counter)
    block_index = cached.block_at(offset)
    return Break(
        block_index=block_index,
        block_name=cached[block_index].name,
        kind=classify(cached, sent, block_index),
        char_offset=offset,
        offset_in_block=offset - cached.start_of(block_index),
        shared_tokens=shared_tokens,
        cached_before=cached_before,
        cached_after=profile.cacheable(shared_tokens),
        counted_exactly=counter is not None,
    )
