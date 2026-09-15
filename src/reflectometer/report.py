"""The whole finding: where the break is, what it threw away, what it costs."""

from __future__ import annotations

from dataclasses import dataclass

from .blocks import Prompt
from .breaks import Break, Refusal, locate
from .cost import Prices, cost_of
from .profiles import EXACT, CacheProfile
from .tokens import TokenCounter, count_tokens


@dataclass(frozen=True)
class BlockLine:
    """One block of the cached prompt, and where it sits against the break."""

    name: str
    tokens: int
    position: str

    def to_dict(self) -> dict:
        return {"name": self.name, "tokens": self.tokens, "position": self.position}


@dataclass(frozen=True)
class Report:
    """A located break, priced at the caller's volume."""

    break_: Break
    profile: CacheProfile
    blocks: tuple[BlockLine, ...]
    prices: Prices | None = None
    calls: int = 1

    @property
    def cost_per_call(self) -> float | None:
        if self.prices is None:
            return None
        return cost_of(self.break_.lost_tokens, self.prices)

    @property
    def cost_per_period(self) -> float | None:
        if self.prices is None:
            return None
        return cost_of(self.break_.lost_tokens, self.prices, self.calls)

    def to_dict(self) -> dict:
        record: dict = {
            "profile": {
                "name": self.profile.name,
                "block_tokens": self.profile.block_tokens,
                "min_prefix_tokens": self.profile.min_prefix_tokens,
            },
            "break": self.break_.to_dict(),
            "blocks": [line.to_dict() for line in self.blocks],
        }
        if self.prices is not None:
            record["cost"] = {
                "input_per_million": self.prices.input_per_million,
                "cache_read_per_million": self.prices.cache_read_per_million,
                "calls": self.calls,
                "per_call": self.cost_per_call,
                "per_period": self.cost_per_period,
            }
        return record

    def __str__(self) -> str:
        from .render import render

        return render(self)


def analyse(
    cached: Prompt,
    sent: Prompt,
    *,
    profile: CacheProfile = EXACT,
    counter: TokenCounter | None = None,
    prices: Prices | None = None,
    calls: int = 1,
) -> Report | Refusal:
    """Locate the break between two prompts and price it.

    ``cached`` is the prompt the provider already holds and ``sent`` is the
    modified copy. Returns a ``Report``, or a ``Refusal`` when there is no
    break to locate.
    """
    found = locate(cached, sent, profile=profile, counter=counter)
    if isinstance(found, Refusal):
        return found
    return Report(
        break_=found,
        profile=profile,
        blocks=_block_lines(cached, found, counter),
        prices=prices,
        calls=calls,
    )


def _block_lines(
    cached: Prompt, found: Break, counter: TokenCounter | None
) -> tuple[BlockLine, ...]:
    lines = []
    for index, block in enumerate(cached):
        if index < found.block_index:
            position = "before break"
        elif index == found.block_index:
            position = "break here"
        else:
            position = "after break"
        lines.append(BlockLine(block.name, count_tokens(block.text, counter), position))
    return tuple(lines)
