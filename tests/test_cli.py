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
    printed = capsys.readouterr().out
    assert "break       left" in printed
    assert "kind        edited" in printed


def test_a_negative_call_count_is_an_error(capsys):
    assert main(["--demo", "--calls", "-5"]) == 1
    assert "--calls cannot be negative" in capsys.readouterr().err


def test_demo_refuses_to_ignore_prompt_files(tmp_path, capsys):
    cached, sent = write_pair(tmp_path, "08:01")
    assert main(["--demo", cached, sent]) == 1
    assert "drop the file arguments" in capsys.readouterr().err


def test_an_unknown_profile_exits_1_so_2_still_means_refusal(capsys):
    assert main(["--demo", "--profile", "nope"]) == 1
    assert "invalid choice: 'nope'" in capsys.readouterr().err


def test_a_prompt_file_over_the_size_limit_is_refused(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("reflectometer.cli.MAX_PROMPT_BYTES", 8)
    path = tmp_path / "big.txt"
    path.write_text("this text is longer than eight bytes")
    assert main([str(path), str(path)]) == 1
    assert "over the 8 byte limit" in capsys.readouterr().err


def test_the_worked_example_in_the_readme_is_what_the_cli_prints(capsys):
    assert (
        main(
            [
                "--demo",
                "--profile",
                "breakpoint-1024",
                "--input-price",
                "3.00",
                "--cache-read-price",
                "0.30",
                "--calls",
                "2000000",
            ]
        )
        == 0
    )
    printed = capsys.readouterr().out
    assert "break       system, character 101 of the prompt" in printed
    assert "3,201 tokens cached · 0 survive · 3,201 thrown away" in printed
    assert "$17,285.40 over 2,000,000 calls" in printed


def test_identical_prompts_exit_with_the_refusal_code(tmp_path, capsys):
    cached, _ = write_pair(tmp_path, "08:00")
    assert main([cached, cached]) == 2
    assert "refused     identical" in capsys.readouterr().out


def test_one_price_without_the_other_is_an_error(capsys):
    assert main(["--demo", "--input-price", "3.0"]) == 1
    assert "pass both" in capsys.readouterr().err


def test_a_missing_file_is_an_error(capsys):
    assert main(["nowhere.json", "nowhere.json"]) == 1
    assert "nowhere.json" in capsys.readouterr().err


def test_a_json_file_that_will_not_parse_is_an_error(tmp_path, capsys):
    path = tmp_path / "broken.json"
    path.write_text('[{"name": "a", "text": "x"},]')
    assert main([str(path), str(path)]) == 1
    printed = capsys.readouterr().err
    assert "broken.json" in printed
    assert "break" not in printed


def test_two_files_are_required(capsys):
    assert main([]) == 1
    assert "two prompt files are required" in capsys.readouterr().err


def test_overrides_replace_the_profile_rules(capsys):
    assert main(["--demo", "--min-prefix", "100000"]) == 2
    assert "below_minimum_prefix" in capsys.readouterr().out


def test_a_block_size_override_changes_what_survives(capsys):
    assert main(["--demo", "--block-tokens", "512", "--json"]) == 0
    assert '"cached_after": 0' in capsys.readouterr().out


def test_a_prompt_file_holding_an_object_is_rejected(tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"name": "system", "text": "x"}))
    assert main([str(path), str(path)]) == 1
    assert "list of blocks" in capsys.readouterr().err


def test_version_is_printed(capsys):
    from reflectometer import __version__

    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"reflectometer {__version__}"


def test_repair_proposes_an_order_and_prices_the_gain(capsys):
    assert (
        main(
            [
                "--split-demo",
                "--repair",
                "--profile",
                "breakpoint-1024",
                "--input-price",
                "3.00",
                "--cache-read-price",
                "0.30",
                "--calls",
                "2000000",
            ]
        )
        == 0
    )
    printed = capsys.readouterr().out
    assert "0 tokens cacheable now · 3,175 after the move" in printed
    assert "$17,145.00 over 2,000,000 calls" in printed
    assert "8  clock       was 1, changes every call" in printed
    assert "9  question    pinned" in printed


def test_repair_writes_json_on_request(capsys):
    assert main(["--split-demo", "--repair", "--json"]) == 0
    record = json.loads(capsys.readouterr().out)
    assert record["volatile"] == ["clock"]
    assert record["pinned"] == ["question"]
    assert record["order"][-2:] == ["clock", "question"]
    assert "saving" not in record


def test_repair_json_carries_the_saving_when_rates_are_given(capsys):
    argv = ["--split-demo", "--repair", "--json", "--profile", "breakpoint-1024"]
    argv += ["--input-price", "3.00"]
    argv += ["--cache-read-price", "0.30", "--calls", "2000000"]
    assert main(argv) == 0
    assert json.loads(capsys.readouterr().out)["saving"] == pytest.approx(17145.0)


def test_the_split_demo_moves_the_break_off_the_system_block(capsys):
    assert main(["--split-demo"]) == 0
    assert "break       clock" in capsys.readouterr().out


def test_repair_refuses_when_no_block_changed(tmp_path, capsys):
    path = tmp_path / "same.json"
    path.write_text(json.dumps([{"name": "a", "text": "same text here"}]))
    assert main([str(path), str(path), "--repair"]) == 2
    assert "nothing_changes" in capsys.readouterr().out
