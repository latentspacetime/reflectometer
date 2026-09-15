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
