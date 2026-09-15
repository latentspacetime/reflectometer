import pytest

from reflectometer import Block, Prompt, plan, profile, rebuild, volatile_blocks
from reflectometer.demo import demo_pair


def pair(cached_pairs, sent_pairs):
    return (
        Prompt([Block(name, text, pinned) for name, text, pinned in cached_pairs]),
        Prompt([Block(name, text, pinned) for name, text, pinned in sent_pairs]),
    )


def test_a_block_that_changed_is_volatile_and_one_that_did_not_is_stable():
    cached, sent = pair(
        [("a", "same", False), ("b", "one", False)],
        [("a", "same", False), ("b", "two", False)],
    )
    assert volatile_blocks(cached, sent) == ("b",)


def test_a_block_missing_from_the_sent_prompt_counts_as_changed():
    cached, sent = pair([("a", "same", False), ("b", "one", False)], [("a", "same", False)])
    assert volatile_blocks(cached, sent) == ("b",)


def test_the_changing_block_moves_below_the_stable_ones():
    cached, sent = pair(
        [("clock", "08:00", False), ("corpus", "text " * 200, False)],
        [("clock", "08:01", False), ("corpus", "text " * 200, False)],
    )
    proposed = plan(cached, sent)
    assert proposed.order == ("corpus", "clock")
    assert proposed.gain == proposed.cacheable_after
    assert proposed.helps


def test_a_pinned_block_keeps_its_position():
    cached, sent = pair(
        [("clock", "08:00", False), ("corpus", "text " * 200, False), ("ask", "q", True)],
        [("clock", "08:01", False), ("corpus", "text " * 200, False), ("ask", "q", True)],
    )
    proposed = plan(cached, sent)
    assert proposed.order == ("corpus", "clock", "ask")
    assert proposed.order[-1] == "ask"


def test_a_pinned_block_that_changes_every_call_caps_the_prefix():
    cached, sent = pair(
        [("ask", "q one", True), ("corpus", "text " * 200, False)],
        [("ask", "q two", True), ("corpus", "text " * 200, False)],
    )
    proposed = plan(cached, sent)
    assert proposed.blocked_by == "ask"
    assert proposed.cacheable_after == 0
    assert not proposed.helps


def test_an_order_that_is_already_right_gains_nothing():
    cached, sent = pair(
        [("corpus", "text " * 200, False), ("clock", "08:00", False)],
        [("corpus", "text " * 200, False), ("clock", "08:01", False)],
    )
    proposed = plan(cached, sent)
    assert proposed.moves == ()
    assert proposed.gain == 0


def test_the_split_demo_recovers_the_prefix_the_timestamp_was_costing():
    cached, sent = demo_pair(split=True)
    proposed = plan(cached, sent, profile=profile("breakpoint-1024"))
    assert proposed.volatile == ("clock",)
    assert proposed.cacheable_now == 0
    assert proposed.cacheable_after == 3159
    assert proposed.order[-2:] == ("clock", "question")


def test_rebuilding_keeps_every_block_and_only_changes_order():
    cached, _ = demo_pair(split=True)
    proposed = plan(*demo_pair(split=True), profile=profile("breakpoint-1024"))
    rebuilt = rebuild(cached, proposed.order)
    assert sorted(rebuilt.names()) == sorted(cached.names())
    assert len(rebuilt.text) == len(cached.text)


def test_an_order_that_drops_a_block_is_rejected():
    cached, _ = demo_pair()
    with pytest.raises(ValueError, match="every block"):
        rebuild(cached, ("system",))


def test_a_plan_says_whether_its_counts_were_exact():
    cached, sent = demo_pair(split=True)
    assert not plan(cached, sent).counted_exactly
    assert plan(cached, sent, counter=len).counted_exactly
