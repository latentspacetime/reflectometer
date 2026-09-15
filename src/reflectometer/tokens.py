"""Token counting.

The cache break itself is a character offset in the prompt, so it does not
depend on how tokens are counted. The size of the loss does. Pass your
provider's tokenizer as a ``TokenCounter`` when you need the loss in exact
tokens, and the default estimator when a close number is enough.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable

TokenCounter = Callable[[str], int]
"""Anything that turns a string into a token count."""

_PIECE = re.compile(r"[A-Za-z]+|\d|\s+|[^\sA-Za-z\d]")


def estimate_tokens(text: str) -> int:
    """Estimate the token count of ``text`` without a tokenizer.

    Letters run together into words, a long word costs about one token per
    four characters, digits and punctuation each cost one, and a run of
    whitespace costs one per line break. The result is an estimate, and every
    report that used it says so.
    """
    total = 0
    for piece in _PIECE.findall(text):
        if piece.isspace():
            total += piece.count("\n")
        elif piece[0].isalpha():
            total += max(1, math.ceil(len(piece) / 4))
        else:
            total += 1
    return total


def count_tokens(text: str, counter: TokenCounter | None = None) -> int:
    """Count tokens with ``counter``, or estimate them when it is absent."""
    return estimate_tokens(text) if counter is None else counter(text)
