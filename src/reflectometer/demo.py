"""A pair of prompts that show the common way a cache dies.

The assistant stamps the current time into its system block, so every call
edits the prompt a hundred characters in, and the retrieved corpus after it is
billed again from scratch.
"""

from __future__ import annotations

from .blocks import Block, Prompt

RULES = [
    "Answer only from the passages supplied below, and say so when they do not cover the question.",
    "Quote the passage identifier beside every claim you take from it.",
    "Give amounts in the units the passage used, and convert only when the reader asked for it.",
    "Keep the answer under six sentences unless the reader asked for a longer one.",
    "Ask one clarifying question when the request names a product the passages never mention.",
]

TOOL_TEXT = (
    "search_docs(query: string, top_k: integer) -> passage[]\n"
    "  Search the product documentation and return the passages that match.\n"
    "open_ticket(summary: string, severity: integer) -> ticket\n"
    "  File a support ticket for a problem the documentation does not solve.\n"
    "check_entitlement(account_id: string) -> plan\n"
    "  Return the support plan an account is entitled to.\n"
)

CHUNK_TOPICS = [
    "retention windows for exported audit logs",
    "rate limits on the batch ingestion endpoint",
    "how a workspace is moved between billing plans",
    "which fields the webhook signature covers",
    "recovering a deleted project inside the grace period",
    "regional storage and where copies are kept",
]


def _system(stamp: str) -> str:
    lines = ["You are the support assistant for a document storage product.", ""]
    lines.append(f"Current date and time: {stamp}.")
    lines.append("")
    lines.extend(f"{position}. {rule}" for position, rule in enumerate(RULES, start=1))
    lines.append("")
    lines.append(
        "Treat every passage below as the only source of truth about the product, and "
        "prefer the most recent passage when two of them disagree."
    )
    return "\n".join(lines) + "\n"


def _chunk(position: int, topic: str) -> str:
    body = " ".join(
        f"Passage {position} sentence {sentence} describes {topic} and the settings an "
        f"administrator changes to control it."
        for sentence in range(1, 13)
    )
    return f"[passage-{position}] {topic}\n{body}\n\n"


def demo_prompts(stamp: str = "2026-09-15 08:00:00 PST") -> Prompt:
    """Build one prompt with ``stamp`` written into the system block."""
    blocks = [Block("system", _system(stamp)), Block("tools", TOOL_TEXT)]
    blocks.extend(
        Block(f"passage-{position}", _chunk(position, topic))
        for position, topic in enumerate(CHUNK_TOPICS, start=1)
    )
    blocks.append(
        Block("question", "Reader: how long are exported audit logs kept?\n", pinned=True)
    )
    return Prompt(blocks)


def demo_pair() -> tuple[Prompt, Prompt]:
    """The prompt the provider cached, and the same prompt one minute later."""
    return demo_prompts(), demo_prompts("2026-09-15 08:01:00 PST")
