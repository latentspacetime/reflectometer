import json

import pytest

from reflectometer.cli import main

BLOCKS = [
    {"name": "system", "text": "time 08:00\n" + "guidance sentence. " * 200},
    {"name": "question", "text": "what is the retention window?", "pinned": True},
]


def write_pair(tmp_path, edit):
    cached = tmp_path / "cached.json"
    sent = tmp_path / "sent.json"
    cached.write_text(json.dumps(BLOCKS))
    changed = [dict(BLOCKS[0], text=BLOCKS[0]["text"].replace("08:00", edit)), BLOCKS[1]]
    sent.write_text(json.dumps(changed))
    return str(cached), str(sent)


def test_demo_runs_and_reports(capsys):
    assert main(["--demo"]) == 0
    assert "cache break between two prompts" in capsys.readouterr().out


def test_json_output_is_machine_readable(capsys):
    assert main(["--demo", "--json"]) == 0
    record = json.loads(capsys.readouterr().out)
    assert record["break"]["block_name"] == "system"


def test_two_files_are_compared(tmp_path, capsys):
    cached, sent = write_pair(tmp_path, "08:01")
    assert main([cached, sent]) == 0
    assert "break       system" in capsys.readouterr().out


def test_a_plain_text_file_becomes_one_block(tmp_path, capsys):
    left, right = tmp_path / "left.txt", tmp_path / "right.txt"
    left.write_text("shared head and left tail")
    right.write_text("shared head and right tail")
    assert main([str(left), str(right)]) == 0
    assert "break       left" in capsys.readouterr().out


def test_identical_prompts_exit_with_the_refusal_code(tmp_path, capsys):
    cached, _ = write_pair(tmp_path, "08:00")
    assert main([cached, cached]) == 2
    assert "refused     identical" in capsys.readouterr().out


def test_one_price_without_the_other_is_an_error(capsys):
    assert main(["--demo", "--input-price", "3.0"]) == 1
    assert "pass both" in capsys.readouterr().err


def test_a_missing_file_is_an_error(capsys):
    assert main(["nowhere.json", "nowhere.json"]) == 1
    assert "reflectometer:" in capsys.readouterr().err


def test_two_files_are_required(capsys):
    assert main([]) == 1
    assert "two prompt files are required" in capsys.readouterr().err


def test_overrides_replace_the_profile_rules(capsys):
    assert main(["--demo", "--min-prefix", "100000"]) == 2
    assert "below_minimum_prefix" in capsys.readouterr().out


def test_a_prompt_file_holding_an_object_is_rejected(tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"name": "system", "text": "x"}))
    assert main([str(path), str(path)]) == 1
    assert "list of blocks" in capsys.readouterr().err


def test_version_is_printed():
    with pytest.raises(SystemExit) as exit_state:
        main(["--version"])
    assert exit_state.value.code == 0
