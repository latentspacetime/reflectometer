"""Text output.

Every line that could be read as an exact token count says whether it is one.
"""

from __future__ import annotations

import textwrap

from .breaks import Break, Refusal
from .cost import Prices, cost_of
from .repair import Repair
from .report import Report

KIND_TEXT = {
    "edited": "text inside the block changed",
    "inserted": "a block was added ahead of it",
    "removed": "a block ahead of it was dropped",
    "reordered": "the same blocks arrived in a new order",
}

REPAIR_NOTES = (
    "Moving a block changes what the model reads, so check the order before sending it.",
    "A block that is only partly volatile keeps the whole block volatile. Split the part\n"
    "      that changes into its own block so the rest can stay on the cached prefix.",
)

NOTES = (
    "A break costs the tokens that come after it, so an edit near the start of a prompt\n"
    "      costs more than an edit near the end, in proportion to the text that follows it.",
    "Cost covers the cached tokens that had to be sent again as ordinary input. Writing the\n"
    "      new prefix into the cache is billed separately by most providers, at a rate above\n"
    "      input, on the call that fills it.",
)


def render(report: Report) -> str:
    found = report.break_
    header = "cache survived this edit" if found.survived else "cache break between two prompts"
    lines = [f"reflectometer · {header}", ""]
    lines.append(f"  profile     {report.profile.name} · {_profile_rule(report)}")
    lines.append(f"  counting    {_counting(found)}")
    lines.append("")
    lines.append(
        f"  break       {found.block_name}, character {found.char_offset:,} of the prompt "
        f"({found.offset_in_block:,} into the block)"
    )
    lines.append(f"  kind        {found.kind} · {KIND_TEXT[found.kind]}")
    lines.append(
        f"  cache       {found.cached_before:,} tokens cached · {found.cached_after:,} survive · "
        f"{found.discarded_tokens:,} thrown away"
    )
    lines.append(f"  rebilled    {found.rebilled_tokens:,} of those tokens are sent again")
    lines.extend(_cost_lines(report))
    lines.append("")
    lines.append("  blocks")
    width = max(len(line.name) for line in report.blocks)
    for line in report.blocks:
        lines.append(f"    {line.name:<{width}}  {line.tokens:>8,} tokens   {line.position}")
    lines.append("")
    lines.append("  notes")
    for note in NOTES:
        lines.append(f"    - {note}")
    return "\n".join(lines)


def render_refusal(refusal: Refusal) -> str:
    detail = textwrap.fill(refusal.detail, width=76, subsequent_indent=" " * 14)
    return "\n".join(
        [
            "reflectometer · no break located",
            "",
            f"  counting    {_counting_text(refusal.counted_exactly)}",
            f"  refused     {refusal.reason}",
            f"  because     {detail}",
        ]
    )


def _profile_rule(report: Report) -> str:
    profile = report.profile
    parts = []
    if profile.block_tokens > 1:
        parts.append(f"{profile.block_tokens}-token blocks")
    if profile.min_prefix_tokens > 0:
        parts.append(f"{profile.min_prefix_tokens}-token minimum prefix")
    return " · ".join(parts) if parts else "every shared token counts"


def _counting(found: Break) -> str:
    return _counting_text(found.counted_exactly)


def _counting_text(exact: bool) -> str:
    if exact:
        return "exact, from the tokenizer you supplied"
    return "estimated, no tokenizer supplied"


def _cost_lines(report: Report) -> list[str]:
    per_call, per_period = report.cost_per_call, report.cost_per_period
    if per_call is None or per_period is None or report.prices is None:
        return [
            "",
            "  cost        not priced; pass your input and cache read rates to get a dollar figure",
        ]
    return [
        "",
        f"  cost        ${per_call:,.4f} per call · ${per_period:,.2f} over {report.calls:,} calls",
        f"              rates ${report.prices.input_per_million:,.2f} input and "
        f"${report.prices.cache_read_per_million:,.2f} cache read, per million tokens",
    ]


def render_repair(repair: Repair, prices: Prices | None = None, calls: int = 1) -> str:
    """Text form of a proposed block order and the prefix it keeps."""
    lines = ["reflectometer · proposed block order", ""]
    lines.append(f"  counting    {_counting_text(repair.counted_exactly)}")
    lines.append(f"  volatile    {', '.join(repair.volatile) if repair.volatile else 'none'}")
    lines.append("")
    lines.append(
        f"  prefix      {repair.cacheable_now:,} tokens cacheable now · "
        f"{repair.cacheable_after:,} after the move · {repair.gain:,} gained"
    )
    if prices is not None and repair.helps:
        saved = cost_of(repair.gain, prices, calls)
        lines.append(f"  saving      ${saved:,.2f} over {calls:,} calls")
    lines.append("")
    lines.append("  order")
    width = max(len(name) for name in repair.order)
    for position, name in enumerate(repair.order):
        moved = next((move for move in repair.moves if move.to_index == position), None)
        notes = []
        if moved is not None:
            notes.append(f"was {moved.from_index}")
        if name in repair.volatile:
            notes.append("changes every call")
        if name in repair.pinned:
            notes.append("pinned")
        suffix = f"   {', '.join(notes)}" if notes else ""
        lines.append(f"    {position}  {name:<{width}}{suffix}".rstrip())
    lines.append("")
    lines.append("  notes")
    for note in REPAIR_NOTES:
        lines.append(f"    - {note}")
    if repair.blocked_by is not None:
        lines.append(
            f"    - {repair.blocked_by} changes every call and is pinned, so it holds the\n"
            "      cacheable prefix where it is."
        )
    return "\n".join(lines)
