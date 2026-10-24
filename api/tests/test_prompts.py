"""The agents' prompts are templates (api/agents/prompts.py); Peak Bar's must render byte for byte as they read before
the placeholders, because recorded AI answers are matched by model + system prompt + input. A change here breaks
every recording the tests replay: change a prompt only together with re-recording (make record)."""

import hashlib
import json
from pathlib import Path

import pytest

from api import accounts
from api.agents import prompts
from api.integrations import replay

RECORDED = Path(replay.FIXTURES)  # data/fixtures

# sha256 of each prompt file as it was before it named the account through {brand}, {brand_kind} and {distributor}
GOLDEN = {
    "coach": "1a0fc11562e50cbe2db990f9e337c43296632aee820b9617a309464d7515af42",
    "investigator": "b05b4422b8351be0410b1b522a3a6461f411c47301ab081ee9d7af457bfbad01",
    "portal_reply": "4082aebe1deea89deaaac2d3760f5a9c71bf99b37762fe44ca7602ca97083a4f",
    "reader": "f4e242bc3fd39f6e524568d00b2a65bb6b175af1b5f4ce74d2562895485b19ef",
    "reader_b": "a32070960b5e0c5f0c6417811c63ba35c96a740601149585f9c4234649198894",
    "rehearsal": "e4401eebaabb4e1a6127e185a5c88248bb0fdb0bf842d548d4ba13695445af41",
    "rule_writer": "5cf28854ac941f275a337149012ed1fb1898de5dee670719c9db74e0c84cd275",
}
# Which prompt each recorded service was asked with.
SERVICES = {
    "claude-reader": "reader", "claude-reader-b": "reader_b", "gemini-reader": "reader_b",
    "claude-investigator": "investigator", "claude-rehearsal": "rehearsal", "claude-portal-reply": "portal_reply",
    "claude-coach": "coach", "claude-rule-writer": "rule_writer",
}


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_peak_bar_renders_every_prompt_byte_for_byte(name):
    text = prompts.render(name, "peak-bar")
    assert hashlib.sha256(text.encode()).hexdigest() == GOLDEN[name]
    assert "{" not in text


@pytest.mark.parametrize("service", sorted(SERVICES))
def test_the_recordings_were_made_with_peak_bars_rendered_prompts(service):
    saved = sorted((RECORDED / service).glob("*.json"))
    if not saved:
        pytest.skip(f"no recordings for {service}")
    systems = {json.loads(p.read_text())["request"]["system"] for p in saved}
    assert prompts.render(SERVICES[service], "peak-bar") in systems


def test_the_default_account_is_peak_bar():
    assert all(prompts.render(n) == prompts.render(n, "peak-bar") for n in GOLDEN)


def test_another_account_gets_its_own_names(two_accounts):
    text = prompts.render("rehearsal", two_accounts)
    assert "Hill Oat Co." in text and "Eastway" in text and "Peak Bar" not in text and "Northmart" not in text
    assert "a small granola brand" in prompts.render("coach", "test-oat")


def test_every_prompt_renders_for_every_account(two_accounts):
    for a in accounts.every():
        for name in prompts.names():
            assert "{" not in prompts.render(name, a, products="Original"), (a.id, name)


def test_an_unknown_placeholder_is_an_error(monkeypatch):
    monkeypatch.setattr(prompts, "_text", lambda name: "You work for {brand} and {nobody}.")
    with pytest.raises(KeyError, match="nobody"):
        prompts.render("reader")
