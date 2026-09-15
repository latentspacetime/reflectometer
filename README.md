# Reflectometer

2026-09-15 00:42 PST

## INTENT

Reflectometer is a Python library that finds the edit that threw away your prompt cache. You give it the prompt your provider already cached and the modified copy you sent next, and it reports the character where the two stop matching, the block you can edit to fix it, how many cached tokens that edit discarded, what those tokens cost at your call volume, and a block order that would keep the cache.

This document covers install, a demo that prints a worked cost calculation, how prefix caching decides what survives, the contents of the report, how to feed your own prompts from Python or from a JSON file, the two provider rules that decide how much of a prefix is cacheable, how to supply a tokenizer so token counts are exact, the six cases that produce a refusal and the exit code each one returns, the proposed block order and what it is worth, how a block marked pinned holds its place, why a block that changes in one line has to be split before it can move, measured evidence that the break address holds under any token counter, the command line arguments, related work, and how to run the tests. License is MIT.

## Install

```
pip install git+https://github.com/latentspacetime/reflectometer
reflectometer --demo --profile breakpoint-1024 --input-price 3.00 --cache-read-price 0.30 --calls 2000000
```

The demo runs on a support assistant whose system block carries the current time, so the prompt changes on every call.

## How a break happens

A provider caches a prompt from the first token forward. On the next call it keeps the cached work up to the first token that differs from what it cached, and everything after that point is computed and billed again. A change near the start of a prompt forces almost the whole prompt to be computed again. A change near the end forces only the tokens that follow it.

Reflectometer reports that position for a given pair of prompts.

## Report

```
reflectometer · cache break between two prompts

  profile     breakpoint-1024 · 1024-token minimum prefix
  counting    estimated, no tokenizer supplied

  break       system, character 101 of the prompt (101 into the block)
  kind        edited · text inside the block changed
  cache       3,201 tokens cached · 0 survive · 3,201 thrown away
  rebilled    3,201 of those tokens are sent again

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
    - A break costs the tokens that come after it, so an edit near the start of a prompt
      costs more than an edit near the end, in proportion to the text that follows it.
    - Cost covers the cached tokens that had to be sent again as ordinary input. Writing the
      new prefix into the cache is billed separately by most providers, at a rate above
      input, on the call that fills it.
```

The output above is what the demo command prints. Character 101 is the timestamp in the system block, 101 characters into a prompt of about 11,000 characters, and it discards every cached token that comes after it, each time the prompt is sent.

A prompt that only grows keeps its cache, so a sent prompt that holds the cached prompt whole and adds to the end of it returns a refusal saying the cached prefix still matches in full. When a sent prompt drops text, it is billed for what it sends. `rebilled` counts the cached tokens the sent prompt still carries after the break. `cache` counts every cached token the provider stopped being able to reuse.

Three lines of the report give what is needed to act:

- `break` gives the block to open and the offset inside it.
- `rebilled` gives the tokens the sent prompt carries after the break, which are the tokens the bill grew by.
- `cost` states the size of the problem in dollars, so it can be ranked against other work.

## Usage

A prompt is a list of blocks in the order they are sent. A block is the unit you can edit, so the report names the block that holds the break:

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
print(report.break_.block_name, report.break_.rebilled_tokens, report.cost_per_period)
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

Block names have to be unique inside a prompt, since the report uses them as addresses. Marking a block `pinned` says it has to keep its position, such as a final user turn, which matters when you decide where a volatile block can move to.

A plain text file is read as a single block named after the file, and the report gives a character offset into that file, which is usable when the prompt is assembled by other code.

Exit code is 0 for a report, 2 for a refusal, and 1 for bad input.

## Cache rules

Two rules decide how much of a shared prefix a provider caches. A provider caches in whole blocks of a fixed size, so a prefix is rounded down to that size, and a provider stores a cache entry only once a prefix reaches a minimum length. That minimum is a breakpoint, so a profile named `breakpoint-N` means the provider stores nothing for a prefix shorter than N tokens. Each profile is named after the cache rule it applies, so the name stays correct when vendor prices and products change:

| Profile | Rule | Use when |
| --- | --- | --- |
| `exact` | every shared token counts | rules are unknown, or you want the upper bound on the loss |
| `block-16` | 16-token blocks | a server that reuses prefixes in small blocks |
| `block-64` | 64-token blocks | a server or API that reuses prefixes in larger blocks |
| `breakpoint-1024` | 1024-token minimum prefix | an API that caches only prefixes above a minimum length |
| `breakpoint-2048` | 2048-token minimum prefix | same rule, larger minimum |

Set the numbers to whatever your provider documents:

```
reflectometer cached.json sent.json --block-tokens 128 --min-prefix 1024
```

Break address is a character offset, so every profile reports the same address. Profile decides how many cached tokens that break is counted as having discarded.

## Repair

A prompt keeps its cache when every volatile block comes after every stable block. `--repair` works out which blocks changed, proposes an order that puts those blocks last, and measures the prefix that order would keep. Both orders are measured by the same code that locates a break, so a proposed order that would shorten the prefix reports a negative gain:

```
reflectometer · proposed block order

  counting    estimated, no tokenizer supplied
  volatile    clock

  prefix      0 tokens cacheable now · 3,175 after the move · 3,175 gained
  saving      $17,145.00 over 2,000,000 calls

  order
    0  system
    1  tools       was 2
    2  passage-1   was 3
    3  passage-2   was 4
    4  passage-3   was 5
    5  passage-4   was 6
    6  passage-5   was 7
    7  passage-6   was 8
    8  clock       was 1, changes every call
    9  question    pinned

  notes
    - Moving a block changes what the model reads, so check the order before sending it.
    - A block that is only partly volatile keeps the whole block volatile. Split the part
      that changes into its own block so the rest can stay on the cached prefix.
```

That output is `reflectometer --split-demo --repair --profile breakpoint-1024 --input-price 3.00 --cache-read-price 0.30 --calls 2000000`.

A pair where no block changed gets a refusal with exit code 2, since no order can keep more of a prompt that is already stable. A block marked `pinned` holds its position, so a final user turn stays last. Every other block keeps its order inside its own group, with the stable group placed first. When the block that changes every call is pinned, the plan says so and reports a gain of zero, because the prefix ends at that block under every order.

A timestamp inside a long system block makes that whole block volatile. Split the changing line into its own block first, and the planner then has a block it can move. `--split-demo` runs the built-in prompts after that split, so it can be compared against `--demo`.

From Python:

```python
from reflectometer import plan, rebuild, profile

proposed = plan(cached, sent, profile=profile("breakpoint-1024"))
print(proposed.volatile, proposed.gain)
fixed = rebuild(cached, proposed.order)
```

`plan` returns an order and `rebuild` applies it to a prompt, so a proposed order takes effect when `rebuild` is called. Moving a block changes what the model reads, so check an order before sending it.

## Token counts

Reflectometer estimates tokens when no tokenizer is supplied, and every report states whether counts came from an estimate or from a supplied tokenizer. Estimated counts are enough to rank one break against another, because both are counted the same way. Pass your provider's tokenizer when discarded token counts have to be exact:

```python
import tiktoken
encoder = tiktoken.get_encoding("o200k_base")
analyse(cached, sent, counter=lambda text: len(encoder.encode(text)))
```

`examples/counters.py` runs one prompt pair under four counters and prints what each one reports:

```
Counter                    Break at   Rebilled   Cost over 2M calls
built-in estimate               101      3,201           17,285.40
one per 4 characters            101      2,759           14,898.60
one per 3 characters            101      3,679           19,866.60
one per whitespace word         101      1,734            9,363.60

Distinct break addresses across 4 counters: 1
Distinct rebilled token counts: 4
```

Break address holds at character 101 under all four counters. Token counts and dollar figures change with the counter, so compare two breaks only when both were counted the same way, and price a break with your provider's tokenizer.

## Refusals

Six conditions produce a refusal with exit code 2, and each refusal says whether its token counts were estimated or exact:

| Refusal | Condition | What it means |
| --- | --- | --- |
| `identical` | the two prompts are the same | cached prefix still matches in full |
| `prefix_intact` | the sent prompt keeps the cached prompt whole and adds to the end | cached prefix still matches in full |
| `nothing_shared` | they differ at the first character | prompts share no prefix, so the provider held no cached tokens for this call |
| `empty_prompt` | the cached prompt holds no tokens | there was nothing to cache |
| `below_minimum_prefix` | the cached prompt is under the profile's minimum prefix | prompt falls under the minimum, so the provider treated it as uncacheable |
| `shorter_than_one_block` | the cached prompt is under one block of the profile | prompt falls under the block size, so the provider treated it as uncacheable |

```
reflectometer · no break located

  counting    estimated, no tokenizer supplied
  refused     below_minimum_prefix
  because     the cached prompt is shorter than the shortest prefix this profile caches,
              so the provider held no cached prefix for it: 3,201 tokens
              against a minimum of 100,000
```

## Arguments

| Argument | Meaning |
| --- | --- |
| `cached` | prompt the provider already holds, required unless `--demo` is given |
| `sent` | modified copy sent on the next call, required unless `--demo` is given |
| `--profile` | cache rule to apply, default `exact` |
| `--block-tokens` | override the profile's block size |
| `--min-prefix` | override the profile's minimum prefix |
| `--input-price` | dollars per million input tokens |
| `--cache-read-price` | dollars per million cached tokens |
| `--calls` | calls to price the break over, default 1 |
| `--json` | write the report as JSON |
| `--repair` | propose a block order that keeps the longest cacheable prefix |
| `--demo` | run on a built-in pair of prompts, so `cached` and `sent` can be left out |
| `--split-demo` | run on the built-in prompts with the changing line in its own block |
| `--version` | print the installed version |

## Related work

Reflectometer takes two prompts from the caller and reports where the cache ended, what it cost, and an order that would keep it. Serving systems including vLLM, SGLang, and Prompt Cache implement prefix caching and decide what to reuse while a request runs. Published work on cache auditing times responses from an endpoint to detect whether a prefix was cached at all, and cost studies compare caching strategies across prompts.

## Development

```
uv venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest
ruff check . && ruff format --check .
```

## License

Reflectometer is released under MIT License.
