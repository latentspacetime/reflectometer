"""Measure how much a token counter changes what the tool reports.

Reflectometer locates a break in characters, so the address should not move
when the counter changes, while every token and dollar figure should. This
script runs one prompt pair under four counters and prints both facts.

    python examples/counters.py
"""

from __future__ import annotations

from reflectometer import Prices, analyse, estimate_tokens, profile
from reflectometer.demo import demo_pair

COUNTERS = {
    "built-in estimate": estimate_tokens,
    "one per 4 characters": lambda text: len(text) // 4,
    "one per 3 characters": lambda text: len(text) // 3,
    "one per whitespace word": lambda text: len(text.split()),
}

PRICES = Prices(input_per_million=3.00, cache_read_per_million=0.30)
CALLS = 2_000_000


def main() -> None:
    cached, sent = demo_pair()
    rows = []
    for name, counter in COUNTERS.items():
        report = analyse(
            cached,
            sent,
            profile=profile("breakpoint-1024"),
            counter=counter,
            prices=PRICES,
            calls=CALLS,
        )
        rows.append((name, report.break_.char_offset, report.break_.rebilled_tokens, report))

    print(f"{'Counter':<24} {'Break at':>10} {'Rebilled':>10} {'Cost over 2M calls':>20}")
    for name, offset, rebilled, report in rows:
        print(f"{name:<24} {offset:>10,} {rebilled:>10,} {report.cost_per_period:>19,.2f}")

    addresses = {offset for _, offset, _, _ in rows}
    print()
    print(f"Distinct break addresses across {len(rows)} counters: {len(addresses)}")
    print(f"Distinct rebilled token counts: {len({rebilled for _, _, rebilled, _ in rows})}")


if __name__ == "__main__":
    main()
