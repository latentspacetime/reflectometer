"""Command line entry point.

Each prompt is a JSON file holding a list of blocks in the order they are sent:

    [{"name": "system", "text": "..."},
     {"name": "passage-1", "text": "..."},
     {"name": "question", "text": "...", "pinned": true}]

A file that is not JSON is read as one block named after the file, which is
enough to get a character offset when the prompt is assembled elsewhere.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .blocks import Block, Prompt, prompt_from_dicts
from .breaks import Refusal
from .cost import Prices
from .demo import demo_pair
from .profiles import PROFILES, CacheProfile, profile
from .render import render_refusal, render_repair
from .repair import plan
from .report import analyse

REFUSED = 2
"""Exit code for a refusal: no break was located, and nothing crashed."""

MAX_PROMPT_BYTES = 64 * 1024 * 1024
"""Largest prompt file that will be read, so a wrong path cannot exhaust memory."""


class Parser(argparse.ArgumentParser):
    """Argument parser that exits 1 on a usage error, leaving 2 for a refusal."""

    def error(self, message: str) -> None:  # type: ignore[override]
        self.exit(1, f"reflectometer: {message}\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as stop:
        return int(stop.code or 0)
    try:
        cached, sent = _load(args)
        prices = _prices(args)
        chosen = _profile(args)
    except (OSError, ValueError) as error:
        print(f"reflectometer: {error}", file=sys.stderr)
        return 1

    if args.repair:
        proposed = plan(cached, sent, profile=chosen)
        if isinstance(proposed, Refusal):
            print(
                json.dumps(proposed.to_dict(), indent=2) if args.json else render_refusal(proposed)
            )
            return REFUSED
        if args.json:
            print(json.dumps(proposed.to_dict(), indent=2))
            return 0
        pinned = [block.name for block in cached if block.pinned]
        print(render_repair(proposed, prices, args.calls, pinned))
        return 0

    result = analyse(cached, sent, profile=chosen, prices=prices, calls=args.calls)
    if isinstance(result, Refusal):
        print(json.dumps(result.to_dict(), indent=2) if args.json else render_refusal(result))
        return REFUSED
    print(json.dumps(result.to_dict(), indent=2) if args.json else str(result))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = Parser(
        prog="reflectometer",
        description="Find the edit that threw away your prompt cache.",
    )
    parser.add_argument("cached", nargs="?", help="the prompt the provider already cached")
    parser.add_argument("sent", nargs="?", help="the modified copy that was sent next")
    parser.add_argument("--demo", action="store_true", help="run on a built-in pair of prompts")
    parser.add_argument(
        "--split-demo",
        action="store_true",
        help="run on the built-in prompts with the changing line in its own block",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default="exact",
        help="cache rule to apply, default exact",
    )
    parser.add_argument("--block-tokens", type=int, help="override the profile's block size")
    parser.add_argument("--min-prefix", type=int, help="override the profile's minimum prefix")
    parser.add_argument("--input-price", type=float, help="dollars per million input tokens")
    parser.add_argument("--cache-read-price", type=float, help="dollars per million cached tokens")
    parser.add_argument(
        "--calls", type=int, default=1, help="calls to price the break over, default 1"
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        help="propose a block order that keeps the longest cacheable prefix",
    )
    parser.add_argument("--json", action="store_true", help="write the report as JSON")
    parser.add_argument("--version", action="version", version=f"reflectometer {__version__}")
    return parser


def _load(args: argparse.Namespace) -> tuple[Prompt, Prompt]:
    if args.demo or args.split_demo:
        flag = "--split-demo" if args.split_demo else "--demo"
        if args.cached or args.sent:
            raise ValueError(f"{flag} runs on its own prompts, so drop the file arguments")
        return demo_pair(split=args.split_demo)
    if not args.cached or not args.sent:
        raise ValueError("two prompt files are required, or --demo")
    return _read(Path(args.cached)), _read(Path(args.sent))


def _read(path: Path) -> Prompt:
    size = path.stat().st_size
    if size > MAX_PROMPT_BYTES:
        raise ValueError(f"{path}: {size:,} bytes is over the {MAX_PROMPT_BYTES:,} byte limit")
    text = path.read_text(encoding="utf-8")
    try:
        records = json.loads(text)
    except json.JSONDecodeError:
        return Prompt([Block(path.stem, text)])
    if not isinstance(records, list):
        raise ValueError(f"{path}: a prompt file holds a list of blocks")
    return prompt_from_dicts(records)


def _prices(args: argparse.Namespace) -> Prices | None:
    if args.calls < 0:
        raise ValueError("--calls cannot be negative")
    if args.input_price is None and args.cache_read_price is None:
        return None
    if args.input_price is None or args.cache_read_price is None:
        raise ValueError("pass both --input-price and --cache-read-price, or neither")
    return Prices(args.input_price, args.cache_read_price)


def _profile(args: argparse.Namespace) -> CacheProfile:
    chosen = profile(args.profile)
    if args.block_tokens is None and args.min_prefix is None:
        return chosen
    return CacheProfile(
        name="custom",
        block_tokens=chosen.block_tokens if args.block_tokens is None else args.block_tokens,
        min_prefix_tokens=chosen.min_prefix_tokens if args.min_prefix is None else args.min_prefix,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
