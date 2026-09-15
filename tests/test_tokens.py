import pytest

from reflectometer import count_tokens, estimate_tokens


def test_an_empty_string_costs_nothing():
    assert estimate_tokens("") == 0


def test_a_long_word_costs_more_than_a_short_one():
    assert estimate_tokens("internationalisation") > estimate_tokens("cat")


def test_the_estimate_grows_with_the_text():
    short = "The retention window is thirty days."
    assert estimate_tokens(short * 4) > estimate_tokens(short)


@pytest.mark.parametrize("text", ["", "a", "one two three", "a\nb\nc", "{}[]()"])
def test_a_supplied_counter_is_used_instead(text):
    assert count_tokens(text, len) == len(text)
    assert count_tokens(text) == estimate_tokens(text)


def test_english_prose_lands_near_the_usual_ratio():
    text = "The assistant answers only from the passages supplied below. " * 50
    ratio = len(text) / estimate_tokens(text)
    assert 3.0 < ratio < 5.5
