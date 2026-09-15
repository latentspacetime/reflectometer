"""Propose a block order that keeps the cache.

A break costs the tokens after it, so a prompt holds its cache best when every
block that changes between calls sits below every block that stays the same.
This module works out which blocks changed, proposes an order that puts the
changing ones last, and measures the prefix that order would keep.

Reordering blocks changes what the model reads, so a plan is a proposal for a
caller to check, and a block marked ``pinned`` is never moved.
"""

from __future__ import annotations

from dataclasses import dataclass

from .blocks import Block, Prompt
from .profiles import EXACT, CacheProfile
from .tokens import TokenCounter, count_tokens


@dataclass(frozen=True)
class Move:
    """One block, and where the plan puts it."""

    name: str
    from_index: int
    to_index: int

    def to_dict(self) -> dict:
        return {"name": self.name, "from_index": self.from_index, "to_index": self.to_index}


@dataclass(frozen=True)
class Repair:
    """A proposed block order, and the prefix it would keep cached."""

    order: tuple[str, ...]
    moves: tuple[Move, ...]
    volatile: tuple[str, ...]
    cacheable_now: int
    cacheable_after: int
    blocked_by: str | None
    counted_exactly: bool

    @property
    def gain(self) -> int:
        """Tokens this order would keep cached that the current order loses."""
        return self.cacheable_after - self.cacheable_now

    @property
    def helps(self) -> bool:
        return self.gain > 0

    def to_dict(self) -> dict:
        return {
            "order": list(self.order),
            "moves": [move.to_dict() for move in self.moves],
            "volatile": list(self.volatile),
            "cacheable_now": self.cacheable_now,
            "cacheable_after": self.cacheable_after,
            "gain": self.gain,
            "blocked_by": self.blocked_by,
            "counted_exactly": self.counted_exactly,
        }


def volatile_blocks(cached: Prompt, sent: Prompt) -> tuple[str, ...]:
    """Names of blocks that changed between the two prompts.

    A block whose name appears in both prompts with the same text is stable.
    Every other block changed, which covers edits, additions, and removals.
    """
    sent_text = {block.name: block.text for block in sent}
    changed = [
        block.name
        for block in cached
        if block.name not in sent_text or sent_text[block.name] != block.text
    ]
    return tuple(changed)


def plan(
    cached: Prompt,
    sent: Prompt,
    *,
    profile: CacheProfile = EXACT,
    counter: TokenCounter | None = None,
) -> Repair:
    """Propose an order for ``cached`` that keeps the longest cacheable prefix.

    Pinned blocks hold their position. Every other block keeps its relative
    order inside its own group, with the stable group placed first.
    """
    changed = set(volatile_blocks(cached, sent))
    free = [index for index, block in enumerate(cached) if not block.pinned]
    stable = [index for index in free if cached[index].name not in changed]
    moving = [index for index in free if cached[index].name in changed]

    order: list[int] = list(range(len(cached)))
    for slot, index in zip(free, stable + moving, strict=True):
        order[slot] = index

    moves = tuple(
        Move(cached[index].name, index, slot) for slot, index in enumerate(order) if index != slot
    )
    proposed = tuple(cached[index].name for index in order)
    return Repair(
        order=proposed,
        moves=moves,
        volatile=tuple(sorted(changed)),
        cacheable_now=profile.cacheable(_stable_prefix(cached, changed, counter)),
        cacheable_after=profile.cacheable(
            _stable_prefix(rebuild(cached, proposed), changed, counter)
        ),
        blocked_by=_blocked_by(rebuild(cached, proposed), changed),
        counted_exactly=counter is not None,
    )


def rebuild(prompt: Prompt, order: tuple[str, ...]) -> Prompt:
    """Return ``prompt`` with its blocks in ``order``, named block by block."""
    by_name = {block.name: block for block in prompt}
    if sorted(order) != sorted(by_name):
        raise ValueError("an order must name every block of the prompt exactly once")
    return Prompt([by_name[name] for name in order])


def _stable_prefix(prompt: Prompt, changed: set[str], counter: TokenCounter | None) -> int:
    """Tokens before the first block that changes between calls."""
    total = 0
    for block in prompt:
        if block.name in changed:
            break
        total += count_tokens(block.text, counter)
    return total


def _blocked_by(prompt: Prompt, changed: set[str]) -> str | None:
    """Name of the pinned changing block that caps the prefix, when there is one."""
    for block in prompt:
        if block.name in changed:
            return block.name if block.pinned else None
    return None


def apply(prompt: Prompt, repair: Repair) -> Prompt:
    """Return ``prompt`` rebuilt in the order ``repair`` proposes."""
    return rebuild(prompt, repair.order)


def block_of(prompt: Prompt, name: str) -> Block:
    """The block called ``name``."""
    for block in prompt:
        if block.name == name:
            return block
    raise ValueError(f"no block named {name!r}")
