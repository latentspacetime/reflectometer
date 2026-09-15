import pytest

from reflectometer import Block, Prompt, prompt_from_dicts


def test_offsets_follow_block_order():
    prompt = Prompt([Block("a", "hello "), Block("b", "world")])
    assert prompt.text == "hello world"
    assert prompt.start_of(0) == 0
    assert prompt.start_of(1) == 6


def test_block_at_maps_an_offset_to_its_block():
    prompt = Prompt([Block("a", "hello "), Block("b", "world")])
    assert prompt.block_at(0) == 0
    assert prompt.block_at(5) == 0
    assert prompt.block_at(6) == 1
    assert prompt.block_at(99) == 1


def test_empty_block_does_not_capture_an_offset_from_its_neighbour():
    prompt = Prompt([Block("a", "abc"), Block("empty", ""), Block("b", "def")])
    assert prompt.block_at(3) == 2


def test_duplicate_names_are_rejected():
    with pytest.raises(ValueError, match="unique"):
        Prompt([Block("a", "x"), Block("a", "y")])


def test_a_prompt_needs_a_block():
    with pytest.raises(ValueError, match="at least one block"):
        Prompt([])


def test_records_become_blocks():
    prompt = prompt_from_dicts(
        [{"name": "system", "text": "s"}, {"name": "q", "text": "q", "pinned": True}]
    )
    assert prompt.names() == ("system", "q")
    assert prompt[1].pinned


@pytest.mark.parametrize(
    ("records", "message"),
    [
        ([{"name": "a"}], "missing"),
        ([{"name": "a", "text": 3}], "non-string"),
        ([{"name": "a", "text": "x", "role": "user"}], "unknown keys"),
        (["system"], "not an object"),
    ],
)
def test_malformed_records_raise(records, message):
    with pytest.raises(ValueError, match=message):
        prompt_from_dicts(records)
