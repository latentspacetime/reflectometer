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
    body = " ".join(f"word{index}" for index in range(2000))
    cached = prompt(("head", "time 08:00\n"), ("body", body))
    sent = prompt(("head", "time 08:01\n"), ("body", body))
    found = locate(cached, sent)
    assert found.block_name == "head"
    assert found.cached_after == 1
    assert found.discarded_tokens > 2000
    assert found.rebilled_tokens == found.discarded_tokens


def test_an_edit_at_the_bottom_costs_almost_nothing():
    body = " ".join(f"word{index}" for index in range(2000))
    cached = prompt(("body", body), ("tail", " tail one"))
    sent = prompt(("body", body), ("tail", " tail two"))
    found = locate(cached, sent)
    assert found.block_name == "tail"
    assert found.cached_before > 2000
    assert found.discarded_tokens == 1
    assert found.rebilled_tokens == 1


def test_the_same_edit_costs_far_more_at_the_top_than_at_the_bottom():
    body = " ".join(f"word{index}" for index in range(2000))
    at_top = locate(
        prompt(("head", "time 08:00\n"), ("body", body)),
        prompt(("head", "time 08:01\n"), ("body", body)),
    )
    at_bottom = locate(
        prompt(("body", body), ("tail", " tail one")),
        prompt(("body", body), ("tail", " tail two")),
    )
    assert at_top.rebilled_tokens > 500 * at_bottom.rebilled_tokens


def test_a_sent_prompt_that_only_adds_text_keeps_its_cache():
    cached = prompt(("body", "shared text"), ("tail", " end"))
    sent = prompt(("body", "shared text"), ("tail", " end and more"))
    result = locate(cached, sent)
    assert isinstance(result, Refusal)
    assert result.reason == "prefix_intact"


def test_a_deletion_is_not_billed_for_tokens_the_sent_prompt_never_carries():
    body = " ".join(f"word{index}" for index in range(2000))
    cached = prompt(("head", "head one "), ("body", body))
    sent = prompt(("head", "head two "))
    found = locate(cached, sent)
    assert found.discarded_tokens > 2000
    assert found.rebilled_tokens <= 2


def test_a_token_straddling_the_break_does_not_survive():
    cached = prompt(("body", "alpha beta gamma"))
    sent = prompt(("body", "alpha beto gamma"))
    found = locate(cached, sent, counter=lambda text: len(text.split()))
    assert found.char_offset == 9
    assert found.cached_after == 1


def test_an_empty_cached_prompt_says_so():
    result = locate(prompt(("a", "")), prompt(("a", "x")))
    assert isinstance(result, Refusal)
    assert result.reason == "empty_prompt"


def test_a_prompt_under_one_block_is_told_apart_from_one_under_the_minimum():
    profile = CacheProfile("test", block_tokens=64)
    result = locate(prompt(("a", "short one")), prompt(("a", "short two")), profile=profile)
    assert isinstance(result, Refusal)
    assert result.reason == "shorter_than_one_block"
    assert "block of 64" in result.detail


def test_a_refusal_says_whether_its_counts_were_exact():
    profile = CacheProfile("test", min_prefix_tokens=1024)
    estimated = locate(prompt(("a", "one")), prompt(("a", "two")), profile=profile)
    exact = locate(prompt(("a", "one")), prompt(("a", "two")), profile=profile, counter=len)
    assert not estimated.counted_exactly
    assert exact.counted_exactly


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
    assert found.cached_before == 1984
    assert found.cached_after == 960
    assert found.shared_tokens > found.cached_after


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
        ((("left", "shared tail"),), (("right", "shared other"),), "edited"),
        ((("a", "x"), ("b", "y"), ("c", "z")), (("a", "q"), ("c", "z"), ("b", "y")), "edited"),
        ((("a", "x"), ("b", "y")), (("b", "y"), ("a", "x")), "reordered"),
        ((("a", "x"), ("b", "y")), (("c", "n"), ("a", "x"), ("b", "y")), "inserted"),
        ((("a", "x"), ("b", "y"), ("c", "z")), (("b", "y"), ("c", "z")), "removed"),
    ],
)
def test_classify_names_the_edit(cached_names, sent_names, expected):
    cached, sent = prompt(*cached_names), prompt(*sent_names)
    assert classify(cached, sent, 0) == expected
