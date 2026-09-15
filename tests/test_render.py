from reflectometer import Block, Prices, Prompt, analyse, locate, profile
from reflectometer.demo import demo_pair, demo_prompts
from reflectometer.render import render_refusal


def test_the_report_names_the_break_and_the_money():
    cached, sent = demo_pair()
    text = str(analyse(cached, sent, prices=Prices(3.0, 0.3), calls=2_000_000))
    assert "break       system" in text
    assert "over 2,000,000 calls" in text
    assert "estimated, no tokenizer supplied" in text


def test_an_unpriced_report_says_how_to_price_it():
    cached, sent = demo_pair()
    assert "pass your input and cache read rates" in str(analyse(cached, sent))


def test_an_exact_count_is_labelled():
    cached, sent = demo_pair()
    assert "exact, from the tokenizer you supplied" in str(
        analyse(cached, sent, counter=lambda text: len(text) // 4)
    )


def test_a_refusal_states_its_reason_and_how_it_counted():
    same = demo_prompts()
    text = render_refusal(locate(same, demo_prompts()))
    assert "no break located" in text
    assert "identical" in text
    assert "estimated, no tokenizer supplied" in text


def test_an_edit_that_costs_nothing_is_not_called_a_break():
    body = " ".join(f"word{index}" for index in range(2000))
    cached = Prompt([Block("head", "head one "), Block("body", body)])
    sent = Prompt([Block("head", "head ")])
    text = str(analyse(cached, sent))
    assert "cache survived this edit" in text
    assert "rebilled    0 of those tokens" in text


def test_the_profile_rule_is_printed():
    cached, sent = demo_pair()
    report = analyse(cached, sent, profile=profile("breakpoint-1024"))
    assert "1024-token minimum prefix" in str(report)
    assert "every shared token counts" in str(analyse(cached, sent))
