import pytest

from reflectometer import Block, CacheProfile, Prompt, Refusal, locate, shared_prefix_length
from reflectometer.breaks import classify


def prompt(*pairs):
    return Prompt([Block(name, text) for name, text in pairs])


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [("", "abc", 0), ("abc", "abd", 2), ("abc", "abc", 3), ("abc", "abcd", 3), ("x", "y", 0)],
)
def test_shared_prefix_length(left, right, expected):
    assert shared_prefix_length(left, right) == expected


def test_break_is_reported_against_the_block_holding_it():
    cached = prompt(("system", "you are helpful. "), ("body", "alpha beta gamma"))
    sent = prompt(("system", "you are helpful. "), ("body", "alpha BETA gamma"))
    found = locate(cached, sent)
    assert found.block_name == "body"
    assert found.offset_in_block == 6
    assert found.char_offset == 23


def test_an_edit_at_the_top_throws_away_everything_after_it():
    cached = prompt(("head", "time 08:00\n"), ("body", "b" * 4000))
    sent = prompt(("head", "time 08:01\n"), ("body", "b" * 4000))
    found = locate(cached, sent)
    assert found.block_name == "head"
    assert found.lost_tokens == found.cached_before - found.cached_after
    assert found.cached_after < 10


def test_an_edit_at_the_bottom_costs_almost_nothing():
    cached = prompt(("body", "b" * 4000), ("tail", "tail one"))
    sent = prompt(("body", "b" * 4000), ("tail", "tail two"))
    found = locate(cached, sent)
    assert found.block_name == "tail"
    assert found.lost_tokens < 5


def test_identical_prompts_refuse():
    cached = prompt(("a", "same text"))
    result = locate(cached, prompt(("a", "same text")))
    assert isinstance(result, Refusal)
    assert result.reason == "identical"


def test_prompts_with_no_shared_prefix_refuse():
    result = locate(prompt(("a", "left")), prompt(("a", "right")))
    assert isinstance(result, Refusal)
    assert result.reason == "nothing_shared"


def test_a_prompt_below_the_minimum_prefix_was_never_cached():
    profile = CacheProfile("test", min_prefix_tokens=1024)
    result = locate(prompt(("a", "short one")), prompt(("a", "short two")), profile=profile)
    assert isinstance(result, Refusal)
    assert result.reason == "below_minimum_prefix"


def test_block_granularity_rounds_the_surviving_prefix_down():
    profile = CacheProfile("test", block_tokens=64)
    cached = prompt(("body", "word " * 2000))
    sent = prompt(("body", "word " * 1000 + "edit " + "word " * 999))
    found = locate(cached, sent, profile=profile)
    assert found.cached_after % 64 == 0
    assert found.cached_before % 64 == 0


def test_an_exact_counter_is_reported_as_exact():
    cached = prompt(("body", "one two three"))
    sent = prompt(("body", "one two four"))
    found = locate(cached, sent, counter=len)
    assert found.counted_exactly
    assert found.shared_tokens == 8


@pytest.mark.parametrize(
    ("cached_names", "sent_names", "expected"),
    [
        ((("a", "x"), ("b", "y")), (("a", "x"), ("b", "z")), "edited"),
        ((("a", "x"), ("b", "y")), (("b", "y"), ("a", "x")), "reordered"),
        ((("a", "x"), ("b", "y")), (("c", "n"), ("a", "x"), ("b", "y")), "inserted"),
        ((("a", "x"), ("b", "y"), ("c", "z")), (("b", "y"), ("c", "z")), "removed"),
    ],
)
def test_classify_names_the_edit(cached_names, sent_names, expected):
    cached, sent = prompt(*cached_names), prompt(*sent_names)
    assert classify(cached, sent, 0) == expected
