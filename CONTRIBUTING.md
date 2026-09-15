# Contributing

Reflectometer finds the edit that invalidated a prompt cache and prices what it threw away. Library holds prompts and arithmetic; caller holds provider.

## Rules

- No runtime dependencies. Library uses only Python standard library, and a change that adds a dependency needs a reason in pull request.
- Break address is a character offset and never depends on how tokens are counted. Anything that makes the address move with the token counter is a bug.
- Every report says whether its token counts came from a supplied tokenizer or from the estimator.
- A prompt pair with no break to locate gets a `Refusal`, not a number with a caveat. Malformed input raises `ValueError`. Those two cases stay separate.
- Prompt structure lives in `blocks.py`, cache rules in `profiles.py`, rates in `cost.py`, location in `breaks.py`, and text output in `render.py`. Keep pure functions pure.

## Checks

```
uv venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest
ruff check . && ruff format --check .
```

All three run in CI on Python 3.10 through 3.13 and must pass before merge.
