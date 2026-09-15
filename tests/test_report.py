import pytest

from reflectometer import Prices, analyse, profile
from reflectometer.demo import demo_pair


def test_the_demo_pair_loses_its_whole_cache_to_a_timestamp():
    cached, sent = demo_pair()
    report = analyse(cached, sent, profile=profile("breakpoint-1024"))
    assert report.break_.block_name == "system"
    assert report.break_.kind == "edited"
    assert report.break_.cached_after == 0
    assert report.break_.lost_tokens == report.break_.cached_before


def test_blocks_are_placed_against_the_break():
    cached, sent = demo_pair()
    report = analyse(cached, sent)
    positions = [line.position for line in report.blocks]
    assert positions[0] == "break here"
    assert set(positions[1:]) == {"after break"}


def test_cost_is_absent_until_rates_are_given():
    cached, sent = demo_pair()
    assert analyse(cached, sent).cost_per_call is None
    priced = analyse(cached, sent, prices=Prices(3.0, 0.3), calls=1000)
    assert priced.cost_per_period == pytest.approx(priced.cost_per_call * 1000)


def test_the_report_round_trips_to_json_shaped_data():
    cached, sent = demo_pair()
    record = analyse(cached, sent, prices=Prices(3.0, 0.3), calls=5).to_dict()
    assert record["break"]["block_name"] == "system"
    assert record["cost"]["calls"] == 5
    assert len(record["blocks"]) == len(cached)
