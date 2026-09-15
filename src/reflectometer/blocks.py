"""Prompt blocks.

A prompt is a list of named blocks in the order they are sent. Blocks are the
unit a caller can actually edit, so a break is reported against a block name
and not only against a character offset.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Block:
    """One editable section of a prompt.

    ``pinned`` marks a block that must keep its position, such as the final
    user turn, so any rewrite of the block order leaves it where it is.
    """

    name: str
    text: str
    pinned: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("block name is required")


class Prompt(Sequence[Block]):
    """An ordered list of blocks, plus the character offsets they occupy."""

    def __init__(self, blocks: Iterable[Block]) -> None:
        self._blocks = tuple(blocks)
        if not self._blocks:
            raise ValueError("a prompt needs at least one block")
        names = [block.name for block in self._blocks]
        if len(set(names)) != len(names):
            raise ValueError(f"block names must be unique, got {sorted(names)}")
        starts: list[int] = []
        offset = 0
        for block in self._blocks:
            starts.append(offset)
            offset += len(block.text)
        self._starts = tuple(starts)
        self._text = "".join(block.text for block in self._blocks)

    @property
    def text(self) -> str:
        """Every block concatenated, which is what the provider hashes."""
        return self._text

    def start_of(self, index: int) -> int:
        """Character offset where block ``index`` begins."""
        return self._starts[index]

    def block_at(self, offset: int) -> int:
        """Index of the block holding character ``offset``.

        An offset at or past the end of the prompt belongs to the last block,
        since that is the block a caller would edit to change it.
        """
        for index in range(len(self._blocks) - 1, -1, -1):
            if offset >= self._starts[index]:
                return index
        return 0

    def names(self) -> tuple[str, ...]:
        return tuple(block.name for block in self._blocks)

    def __getitem__(self, index):  # type: ignore[override]
        return self._blocks[index]

    def __len__(self) -> int:
        return len(self._blocks)

    def __iter__(self) -> Iterator[Block]:
        return iter(self._blocks)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Prompt) and self._blocks == other._blocks

    def __repr__(self) -> str:
        return f"Prompt({list(self._blocks)!r})"


def prompt_from_dicts(records: Iterable[dict]) -> Prompt:
    """Build a prompt from JSON records of the form ``{"name": ..., "text": ...}``."""
    blocks = []
    for position, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"block {position} is not an object")
        missing = {"name", "text"} - set(record)
        if missing:
            raise ValueError(f"block {position} is missing {sorted(missing)}")
        unknown = set(record) - {"name", "text", "pinned"}
        if unknown:
            raise ValueError(f"block {position} has unknown keys {sorted(unknown)}")
        if not isinstance(record["text"], str):
            raise ValueError(f"block {position} has a non-string text")
        blocks.append(
            Block(
                name=str(record["name"]),
                text=record["text"],
                pinned=bool(record.get("pinned", False)),
            )
        )
    return Prompt(blocks)
