# Contributing

2026-09-15 01:12 PST

## INTENT

This document tells anyone changing Reflectometer what the library is for and what it has to keep doing. Reflectometer takes two prompts, finds the edit that ended a prompt cache, and prices what that edit threw away. Rules below cover seven things: library stays on the Python standard library; break address is measured in characters so it holds under any token counter; every report names where its token counts came from; a prompt pair with nothing to find returns a `Refusal` while broken input raises `ValueError`; a block order is returned for a person to apply; every README claim about how far a number moves comes from a run of `examples/counters.py`; and each concern lives in its own module. Last section lists the three commands that have to pass before a change merges.

## Rules

- Library runs on the Python standard library alone, and a change that adds a dependency needs a reason in the pull request.
- Break address is a character offset, fixed by the text of the two prompts alone. Anything that makes the address move with the token counter is a bug.
- Every report and every refusal says whether its token counts came from a supplied tokenizer or from the estimator.
- A prompt pair with no break to locate gets a `Refusal` that names the condition. Malformed input raises `ValueError`, which is a separate path and stays that way.
- `plan` returns a proposed block order and `rebuild` applies one, so a proposal changes a prompt when the caller calls `rebuild`. A block marked `pinned` holds its position in every order `plan` returns.
- Every surviving prefix, wherever it is reported, is measured by `cached_prefix` in `breaks.py`. A second way of counting a prefix will disagree with the first one and send a caller the wrong way.
- Every claim in README about how far a number moves is measured. `examples/counters.py` runs one prompt pair under four token counters, and any README statement about counter sensitivity comes from a run of that script.
- Prompt structure lives in `blocks.py`, cache rules in `profiles.py`, rates in `cost.py`, location in `breaks.py`, block order in `repair.py`, and text output in `render.py`. Functions in these modules take their input as arguments and return their result, without reading files, printing, or holding state.

## Checks

```
uv venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

All three run in CI on Python 3.10 through 3.13 and must pass before merge.
