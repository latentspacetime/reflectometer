"""Text output.

Every line that could be read as an exact token count says whether it is one.
"""

from __future__ import annotations

import textwrap

from .breaks import Break, Refusal
from .report import Report

KIND_TEXT = {
    "edited": "text inside the block changed",
    "inserted": "a block was added ahead of it",
    "removed": "a block ahead of it was dropped",
    "reordered": "the same blocks arrived in a new order",
}

NOTES = (
    "A break costs the tokens after it, so an edit near the top of a prompt costs far\n"
    "      more than the same edit near the bottom.",
    "Cost counts the cached tokens that had to be sent again as ordinary input. It does\n"
    "      not count writing the new prefix into the cache, which most providers bill at a\n"
    "      higher rate than input on the call that fills it.",
)


def render(report: Report) -> str:
    found = report.break_
    lines = ["reflectometer · cache break between two prompts", ""]
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
        f"{found.lost_tokens:,} thrown away"
    )
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
    if found.counted_exactly:
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
