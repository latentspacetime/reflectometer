# Reflectometer

2026-09-15 00:42 PST

## Intent

Reflectometer is a Python library that finds the edit that threw away your prompt cache. You give it the prompt your provider already cached and the modified copy you sent next, and it reports the exact character where the two stopped matching, the block you can edit to fix it, how many cached tokens that edit discarded, and what those tokens cost at your call volume. This document covers install, a demo whose cost is worked out on screen, how prefix caching decides what survives, the contents of the report, how to feed your own prompts from Python or from a JSON file, the two provider rules that decide how much of a prefix is cacheable, how to get exact token counts instead of estimates, the three cases that produce a refusal instead of a report, the command line arguments, related work, and how to run the tests. License is MIT.

## Install

```
pip install git+https://github.com/latentspacetime/reflectometer
reflectometer --demo --profile breakpoint-1024 --input-price 3.00 --cache-read-price 0.30 --calls 2000000
```

Demo runs on a support assistant whose system block carries the current time, which is the most common way a cache dies.

## How a break happens

A provider caches a prompt from the first token forward. On the next call it keeps the cached work up to the first token that differs from what it cached, and everything after that point is computed and billed again. One character changed near the top of a prompt therefore costs the whole prompt, and the same change near the bottom costs almost nothing.

That makes the position of an edit the thing that decides the bill. Reflectometer finds that position.

## Report

```
reflectometer · cache break between two prompts

  profile     breakpoint-1024 · 1024-token minimum prefix
  counting    estimated, no tokenizer supplied

  break       system, character 101 of the prompt (101 into the block)
  kind        edited · text inside the block changed
  cache       3,201 tokens cached · 0 survive · 3,201 thrown away

  cost        $0.0086 per call · $17,285.40 over 2,000,000 calls
              rates $3.00 input and $0.30 cache read, per million tokens

  blocks
    system          218 tokens   break here
    tools           122 tokens   after break
    passage-1       455 tokens   after break
    passage-2       468 tokens   after break
    passage-3       494 tokens   after break
    passage-4       468 tokens   after break
    passage-5       507 tokens   after break
    passage-6       455 tokens   after break
    question         14 tokens   after break

  notes
    - A break costs the tokens after it, so an edit near the top of a prompt costs far
      more than the same edit near the bottom.
    - Cost counts the cached tokens that had to be sent again as ordinary input. It does
      not count writing the new prefix into the cache, which most providers bill at a
      higher rate than input on the call that fills it.
```

That output is the demo command above. Character 101 is the timestamp in the system block, 101 characters into a prompt of eleven thousand, and it discards every cached token below it on every call.

Three lines usually decide what to do next. `break` gives the block to open and the offset inside it, `blocks` shows how much text sits below the break and is therefore being paid for again, and `cost` states the size of the problem in dollars so it can be ranked against other work.

## Usage

A prompt is a list of blocks in the order they are sent. Blocks are the unit you can actually edit, so the report names one:

```python
from reflectometer import Block, Prompt, Prices, analyse, profile

cached = Prompt([
    Block("system", "You are a support assistant.\nCurrent time: 08:00.\n"),
    Block("passages", corpus_text),
    Block("question", "How long are audit logs kept?", pinned=True),
])
sent = Prompt([
    Block("system", "You are a support assistant.\nCurrent time: 08:01.\n"),
    Block("passages", corpus_text),
    Block("question", "How long are audit logs kept?", pinned=True),
])

report = analyse(
    cached, sent,
    profile=profile("breakpoint-1024"),
    prices=Prices(input_per_million=3.00, cache_read_per_million=0.30),
    calls=2_000_000,
)
print(report)
print(report.break_.block_name, report.break_.lost_tokens, report.cost_per_period)
```

From the command line, each prompt is a JSON file holding the same list:

```json
[{"name": "system", "text": "You are a support assistant.\nCurrent time: 08:00.\n"},
 {"name": "passages", "text": "..."},
 {"name": "question", "text": "How long are audit logs kept?", "pinned": true}]
```

```
reflectometer cached.json sent.json --profile breakpoint-1024
reflectometer cached.json sent.json --json > break.json
```

A file that is not JSON is read as one block named after the file, which still gives a character offset when the prompt is assembled somewhere else.

Exit code is 0 for a report, 2 for a refusal, and 1 for bad input.

## Cache rules

Two published rules decide how much of a shared prefix a provider would have cached. A provider caches in whole blocks of a fixed size, so a prefix is rounded down to that size, and a provider refuses to cache a prefix shorter than a minimum. Profiles are named after the rule they apply rather than after a vendor, so the name stays correct when prices and products change:

| Profile | Rule | Use when |
| --- | --- | --- |
| `exact` | every shared token counts | rules are unknown, or you want the upper bound on the loss |
| `block-16` | 16-token blocks | a server that reuses prefixes in small blocks |
| `block-64` | 64-token blocks | a server or API that reuses prefixes in larger blocks |
| `breakpoint-1024` | 1024-token minimum prefix | an API that refuses to cache a short prefix |
| `breakpoint-2048` | 2048-token minimum prefix | same rule, larger minimum |

Set the numbers to whatever your provider documents:

```
reflectometer cached.json sent.json --block-tokens 128 --min-prefix 1024
```

The break address is a character offset, so it is the same under every profile. The profile changes how many cached tokens that break is counted as having discarded.

## Token counts

Reflectometer estimates tokens when no tokenizer is supplied, and every report says which of the two it used. The estimate is enough to rank one break against another, since both are counted the same way. Pass your provider's tokenizer when the loss has to be exact:

```python
import tiktoken
encoder = tiktoken.get_encoding("o200k_base")
analyse(cached, sent, counter=lambda text: len(encoder.encode(text)))
```

The break address does not move when the counter changes, because it is measured in characters.

## Refusals

Three conditions mean there is no break to locate, and each returns a refusal with exit code 2 instead of a report:

| Refusal | Condition | What it means |
| --- | --- | --- |
| `identical` | the two prompts are the same | no cache was broken |
| `nothing_shared` | they differ at the first character | no prefix was ever shared, so nothing was cached to lose |
| `below_minimum_prefix` | the cached prompt is shorter than the profile's minimum | the provider never cached this prompt |

```
reflectometer · no break located

  refused     below_minimum_prefix
  because     the original prompt is shorter than the shortest prefix this profile caches,
              so there was no cache to break (3,201 tokens against a minimum of 100000
              under profile custom)
```

## Arguments

| Argument | Meaning |
| --- | --- |
| `cached` | prompt the provider already holds |
| `sent` | modified copy sent on the next call |
| `--profile` | cache rule to apply, default `exact` |
| `--block-tokens` | override the profile's block size |
| `--min-prefix` | override the profile's minimum prefix |
| `--input-price` | dollars per million input tokens |
| `--cache-read-price` | dollars per million cached tokens |
| `--calls` | calls to price the break over, default 1 |
| `--json` | write the report as JSON |
| `--demo` | run on a built-in pair of prompts |

## Related work

Prefix caching is implemented by serving systems including vLLM, SGLang, and Prompt Cache, which decide what to reuse while a request is running. Published work on cache auditing detects whether a prefix was cached at all, usually with a timing test against an endpoint, and cost studies compare caching strategies across prompts.

Reflectometer takes two prompts you already have and returns the address of the edit between them that ended the cache, the count of tokens it discarded, and the dollars that comes to at your volume.

## Development

```
uv venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest
ruff check . && ruff format --check .
```

## License

MIT
