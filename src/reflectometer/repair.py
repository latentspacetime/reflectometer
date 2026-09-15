"""Propose a block order that keeps the cache.

A break costs the tokens after it, so a prompt holds its cache best when every
block that changes between calls comes after every block that stays the same.
This module works out which blocks changed, proposes an order that puts the
changing ones last, and measures what that order would keep by running the
same prefix measurement the break locator uses.

Reordering blocks changes what the model reads, so a plan is a proposal for a
caller to check, and a block marked ``pinned`` is never moved.
"""

from __future__ import annotations

from dataclasses import dataclass

from .blocks import Prompt
from .breaks import Refusal, cached_prefix
from .profiles import EXACT, CacheProfile
from .tokens import TokenCounter

NOTHING_CHANGES = "no block changed between the two prompts, so no order can keep more of it"


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
    pinned: tuple[str, ...]
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

    def __str__(self) -> str:
        from .render import render_repair

        return render_repair(self)

    def to_dict(self) -> dict:
        return {
            "order": list(self.order),
            "moves": [move.to_dict() for move in self.moves],
            "volatile": list(self.volatile),
            "pinned": list(self.pinned),
            "cacheable_now": self.cacheable_now,
            "cacheable_after": self.cacheable_after,
            "gain": self.gain,
            "blocked_by": self.blocked_by,
            "counted_exactly": self.counted_exactly,
        }


def volatile_blocks(cached: Prompt, sent: Prompt) -> tuple[str, ...]:
    """Names of blocks that changed between the two prompts.

    A block whose name appears in both prompts with the same text is stable.
    Every other name changed, which covers edits, blocks dropped from the sent
    prompt, and blocks added to it.
    """
    cached_text = {block.name: block.text for block in cached}
    sent_text = {block.name: block.text for block in sent}
    changed = [name for name in cached.names() if cached_text[name] != sent_text.get(name)]
    changed.extend(name for name in sent.names() if name not in cached_text)
    return tuple(changed)


def plan(
    cached: Prompt,
    sent: Prompt,
    *,
    profile: CacheProfile = EXACT,
    counter: TokenCounter | None = None,
) -> Repair | Refusal:
    """Propose an order for ``cached`` that keeps the longest cacheable prefix.

    Pinned blocks hold their position. Every other block keeps its relative
    order inside its own group, with the stable group placed first. Both orders
    are measured by rebuilding the pair and reading the prefix that survives,
    so a plan that would shorten the prefix reports a negative gain.
    """
    exact = counter is not None
    changed = volatile_blocks(cached, sent)
    if not changed:
        return Refusal("nothing_changes", NOTHING_CHANGES, exact)

    changing = set(changed)
    free = [index for index, block in enumerate(cached) if not block.pinned]
    stable = [index for index in free if cached[index].name not in changing]
    moving = [index for index in free if cached[index].name in changing]

    layout: list[int] = list(range(len(cached)))
    for slot, index in zip(free, stable + moving, strict=True):
        layout[slot] = index

    order = tuple(cached[index].name for index in layout)
    moves = tuple(
        Move(cached[index].name, index, slot) for slot, index in enumerate(layout) if index != slot
    )
    after = (reorder(cached, order), reorder(sent, order))
    return Repair(
        order=order,
        moves=moves,
        volatile=tuple(sorted(changing)),
        pinned=tuple(block.name for block in cached if block.pinned),
        cacheable_now=cached_prefix(cached, sent, profile=profile, counter=counter),
        cacheable_after=cached_prefix(*after, profile=profile, counter=counter),
        blocked_by=_blocked_by(after[0], changing),
        counted_exactly=exact,
    )


def rebuild(prompt: Prompt, order: tuple[str, ...]) -> Prompt:
    """Return ``prompt`` with its blocks in ``order``, named block by block."""
    by_name = {block.name: block for block in prompt}
    if sorted(order) != sorted(by_name):
        raise ValueError("an order must name every block of the prompt exactly once")
    return Prompt([by_name[name] for name in order])


def reorder(prompt: Prompt, order: tuple[str, ...]) -> Prompt:
    """Return ``prompt`` following ``order`` as far as it applies.

    Names the prompt does not hold are skipped, and names the order does not
    mention keep their relative position at the end, so the two prompts of a
    pair can be measured under one order even when their blocks differ.
    """
    by_name = {block.name: block for block in prompt}
    named = [by_name[name] for name in order if name in by_name]
    rest = [block for block in prompt if block.name not in set(order)]
    return Prompt(named + rest)


def _blocked_by(prompt: Prompt, changing: set[str]) -> str | None:
    """Name of the pinned changing block that caps the prefix, when there is one."""
    for block in prompt:
        if block.name not in changing:
            continue
        return block.name if block.pinned else None
    return None
