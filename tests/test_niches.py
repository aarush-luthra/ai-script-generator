import re

import pytest

from engine.budget import make_budget
from engine.checks import check_script
from engine.niches import NICHES, get_playbook
from engine.schemas import Script


@pytest.mark.parametrize("niche", list(NICHES))
def test_every_playbook_loads_with_required_sections(niche):
    pb = get_playbook(niche)
    for section in ("## What counts as a specific", "## Hooks that work here", "## Pitfalls", "## Example scripts"):
        assert section in pb.text
    assert pb.banned_phrases and pb.editor_checks


@pytest.mark.parametrize("niche", list(NICHES))
def test_example_scripts_pass_our_own_checks(niche):
    """The quality bar we show the model must itself pass every rule we enforce."""
    pb = get_playbook(niche)
    examples = pb.text.split("## Example scripts")[1].split("### ")[1:]
    assert len(examples) == 2
    for block in examples:
        seconds = int(re.search(r"· (\d+)s", block).group(1))
        hook, body, cta = (re.search(rf"\*\*{k}:\*\* (.*)", block).group(1) for k in ("Hook", "Body", "CTA"))
        assert check_script(Script(hook=hook, body=body, cta=cta), make_budget(seconds), pb.banned_phrases) == []


def test_aliases_and_unknown_niches():
    assert get_playbook("cooking").name == "Food & restaurants"
    assert get_playbook("  Tech ").name == "Tech"
    assert get_playbook("underwater basket weaving") is None


def test_niche_banned_phrases_are_enforced():
    pb = get_playbook("Food & restaurants")
    script = Script(hook="This taco spot is a hidden gem.", body="word " * 60, cta="Go.")
    issues = check_script(script, make_budget(30), pb.banned_phrases)
    assert any("hidden gem" in i.message for i in issues)


def test_only_the_writer_gets_the_example_scripts():
    from engine import prompts
    from engine.schemas import Brief

    brief = Brief("Food & restaurants", "best pizza in LA", 45, "conversational")
    assert "## Example scripts" in prompts.script_instructions(brief)
    assert "## Example scripts" not in prompts.directions_instructions(brief)
    assert "What counts as a specific" in prompts.directions_instructions(brief)
