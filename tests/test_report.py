import pytest

from reflectometer import Block, Prices, Prompt, analyse, locate, profile
from reflectometer.demo import demo_pair, demo_prompts


def test_the_demo_pair_loses_its_whole_cache_to_a_timestamp():
    cached, sent = demo_pair()
    report = analyse(cached, sent, profile=profile("breakpoint-1024"))
    assert report.break_.block_name == "system"
    assert report.break_.kind == "edited"
    assert report.break_.cached_after == 0
    assert report.break_.rebilled_tokens == report.break_.cached_before


def test_the_worked_example_in_the_readme_still_holds():
    cached, sent = demo_pair()
    report = analyse(
        cached,
        sent,
        profile=profile("breakpoint-1024"),
        prices=Prices(3.00, 0.30),
        calls=2_000_000,
    )
    assert report.break_.char_offset == 101
    assert report.break_.cached_before == 3201
    assert report.break_.rebilled_tokens == 3201
    assert report.cost_per_period == pytest.approx(17285.40)


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
    assert priced.cost_per_call == pytest.approx(0.0085482)
    assert priced.cost_per_period == pytest.approx(8.5482)


def test_the_report_round_trips_to_json_shaped_data():
    cached, sent = demo_pair()
    record = analyse(cached, sent, prices=Prices(3.0, 0.3), calls=5).to_dict()
    assert record["break"]["block_name"] == "system"
    assert record["cost"]["calls"] == 5
    assert len(record["blocks"]) == len(cached)


def test_every_edit_kind_survives_the_whole_path(tmp_path):
    head = Block("head", "shared head text that both prompts carry\n")
    body = Block("body", "body text " * 50)
    extra = Block("extra", "added block\n")
    tail = Block("tail", "tail text\n")

    inserted = analyse(Prompt([head, body, tail]), Prompt([head, extra, body, tail]))
    removed = analyse(Prompt([head, extra, body, tail]), Prompt([head, body, tail]))
    reordered = analyse(Prompt([head, body, tail]), Prompt([head, tail, body]))

    assert inserted.break_.kind == "inserted"
    assert removed.break_.kind == "removed"
    assert reordered.break_.kind == "reordered"
    for report in (inserted, removed, reordered):
        assert report.break_.block_name in {"body", "extra", "tail"}
        assert str(report).count("kind") == 1


def test_a_refusal_prints_the_same_text_the_command_line_prints():
    from reflectometer.render import render_refusal

    same = demo_prompts()
    refusal = locate(same, demo_prompts())
    assert str(refusal) == render_refusal(refusal)
