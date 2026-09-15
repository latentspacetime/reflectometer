"""Locate the edit that broke the cache.

A prefix cache survives up to the first character where the new prompt stops
matching the old one. Everything the provider had cached past that point is
thrown away and billed again. This module finds that character, names the
block that holds it, and counts what it cost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

from .blocks import Prompt
from .profiles import EXACT, CacheProfile
from .tokens import TokenCounter, count_tokens

Kind = Literal["edited", "inserted", "removed", "reordered"]

REFUSALS = {
    "identical": "the two prompts are the same, so the cached prefix still matches in full",
    "prefix_intact": (
        "the sent prompt keeps the cached prompt whole and adds to the end of it, so the "
        "cached prefix still matches in full"
    ),
    "nothing_shared": (
        "the prompts differ at the first character, so the provider held no cached prefix "
        "for this call"
    ),
    "empty_prompt": "the cached prompt holds no tokens, so there was nothing to cache",
    "below_minimum_prefix": (
        "the cached prompt is shorter than the shortest prefix this profile caches, so the "
        "provider held no cached prefix for it"
    ),
    "shorter_than_one_block": (
        "the cached prompt is shorter than one cache block under this profile, so the "
        "provider held no cached prefix for it"
    ),
}

_TRAILING_PARTIAL = re.compile(r"\S+$")


@dataclass(frozen=True)
class Refusal:
    """A case where no break can be located, and why."""

    reason: str
    detail: str
    counted_exactly: bool = True

    def __str__(self) -> str:
        from .render import render_refusal

        return render_refusal(self)

    def to_dict(self) -> dict:
        return {
            "refused": self.reason,
            "because": self.detail,
            "counted_exactly": self.counted_exactly,
        }


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
    sent_tokens: int
    counted_exactly: bool

    @property
    def discarded_tokens(self) -> int:
        """Cached tokens the provider stopped being able to reuse."""
        return self.cached_before - self.cached_after

    @property
    def rebilled_tokens(self) -> int:
        """Discarded tokens the sent prompt still carries, so they are billed again.

        A sent prompt that is shorter than the cached one does not pay for the
        tokens it dropped, so the billed count is capped by what it sends.
        """
        return max(0, min(self.cached_before, self.sent_tokens) - self.cached_after)

    @property
    def survived(self) -> bool:
        """True when this edit costs nothing, because no cached token was rebilled."""
        return self.rebilled_tokens == 0

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
            "sent_tokens": self.sent_tokens,
            "discarded_tokens": self.discarded_tokens,
            "rebilled_tokens": self.rebilled_tokens,
            "counted_exactly": self.counted_exactly,
        }


def shared_prefix_length(left: str, right: str) -> int:
    """Number of leading characters the two strings agree on.

    Bisects rather than scanning character by character, because prompts run to
    tens of thousands of characters and slice comparison runs in C.
    """
    limit = min(len(left), len(right))
    if left[:limit] == right[:limit]:
        return limit
    low, high = 0, limit
    while low < high:
        middle = (low + high + 1) // 2
        if left[:middle] == right[:middle]:
            low = middle
        else:
            high = middle - 1
    return low


def surviving_prefix(text: str, offset: int) -> str:
    """Longest prefix of ``text`` before ``offset`` that ends on a token boundary.

    A token that straddles the break cannot survive, and no tokenizer is needed
    to know that the run of non-whitespace containing the break is spent.
    """
    if offset >= len(text):
        return text[:offset]
    return _TRAILING_PARTIAL.sub("", text[:offset])


def shared_tokens_between(cached: str, sent: str, counter: TokenCounter | None) -> tuple[int, int]:
    """Break offset between two prompt texts, and the tokens that survive it."""
    offset = shared_prefix_length(cached, sent)
    return offset, count_tokens(surviving_prefix(cached, offset), counter)


def cached_prefix(
    cached: Prompt,
    sent: Prompt,
    *,
    profile: CacheProfile = EXACT,
    counter: TokenCounter | None = None,
) -> int:
    """Tokens of ``cached`` the provider can still reuse when ``sent`` arrives.

    Every measurement of a surviving prefix goes through this function, so a
    prefix means the same thing wherever it is reported.
    """
    _, shared = shared_tokens_between(cached.text, sent.text, counter)
    return profile.cacheable(shared)


def classify(cached: Prompt, sent: Prompt, block_index: int) -> Kind:
    """Name the edit that produced the break at ``block_index`` of the cached prompt.

    Block names are aligned between the two prompts. A block that still sits at
    the same position under the same name was edited in place, a permutation of
    the same names is a reorder, and anything else is read from the alignment.
    """
    old_names, new_names = list(cached.names()), list(sent.names())
    if block_index < len(new_names) and new_names[block_index] == old_names[block_index]:
        return "edited"
    if sorted(old_names) == sorted(new_names):
        return "reordered"
    matcher = SequenceMatcher(a=old_names, b=new_names, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal" or i1 > block_index:
            continue
        if tag == "replace" and (i2 - i1) == (j2 - j1):
            return "edited"
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
    exact = counter is not None
    old_text, new_text = cached.text, sent.text
    if old_text == new_text:
        return Refusal("identical", REFUSALS["identical"], exact)

    total_tokens = count_tokens(old_text, counter)
    cached_before = profile.cacheable(total_tokens)
    if cached_before == 0:
        return Refusal(*_nothing_cached(profile, total_tokens), exact)

    offset = shared_prefix_length(old_text, new_text)
    if offset == 0:
        return Refusal("nothing_shared", REFUSALS["nothing_shared"], exact)
    if offset == len(old_text):
        return Refusal("prefix_intact", REFUSALS["prefix_intact"], exact)

    _, shared_tokens = shared_tokens_between(old_text, new_text, counter)
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
        sent_tokens=count_tokens(new_text, counter),
        counted_exactly=exact,
    )


def _nothing_cached(profile: CacheProfile, total_tokens: int) -> tuple[str, str]:
    """Say which of the profile's rules kept this prompt out of the cache."""
    if total_tokens == 0:
        return "empty_prompt", REFUSALS["empty_prompt"]
    if total_tokens < profile.min_prefix_tokens:
        return "below_minimum_prefix", (
            f"{REFUSALS['below_minimum_prefix']}: {total_tokens:,} tokens against a "
            f"minimum of {profile.min_prefix_tokens:,}"
        )
    return "shorter_than_one_block", (
        f"{REFUSALS['shorter_than_one_block']}: {total_tokens:,} tokens against a block "
        f"of {profile.block_tokens:,}"
    )
