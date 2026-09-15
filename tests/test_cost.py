import pytest

from reflectometer import CacheProfile, Prices, cost_of


def test_cost_is_the_difference_between_the_two_rates():
    prices = Prices(input_per_million=3.0, cache_read_per_million=0.3)
    assert cost_of(1_000_000, prices) == pytest.approx(2.7)
    assert cost_of(1_000_000, prices, calls=10) == pytest.approx(27.0)


def test_a_cache_read_cannot_cost_more_than_input():
    with pytest.raises(ValueError, match="not a cache"):
        Prices(input_per_million=1.0, cache_read_per_million=2.0)


def test_negative_inputs_are_rejected():
    prices = Prices(3.0, 0.3)
    with pytest.raises(ValueError):
        cost_of(-1, prices)
    with pytest.raises(ValueError):
        cost_of(1, prices, calls=-1)
    with pytest.raises(ValueError):
        Prices(-1.0, 0.0)


@pytest.mark.parametrize(
    ("tokens", "block", "minimum", "expected"),
    [(100, 1, 0, 100), (100, 64, 0, 64), (63, 64, 0, 0), (100, 1, 1024, 0), (2000, 1, 1024, 2000)],
)
def test_cacheable_applies_both_rules(tokens, block, minimum, expected):
    profile = CacheProfile("test", block_tokens=block, min_prefix_tokens=minimum)
    assert profile.cacheable(tokens) == expected


def test_a_profile_needs_a_positive_block_size():
    with pytest.raises(ValueError, match="block_tokens"):
        CacheProfile("test", block_tokens=0)
