"""Niche playbooks: what "good" means for a specific kind of creator.

Each niche has a Markdown file in this folder with the audience, what counts as
a specific, formats, hooks, pitfalls, closes, editor checks and two hand-written
example scripts. The whole file goes into the prompts; the "Banned phrases" list
is also enforced in code. Unknown niches fall back to the generic craft rules.
"""

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

HERE = Path(__file__).parent

# Display name -> playbook file. Order is the order shown in the UI.
NICHES = {
    "Food & restaurants": "food",
    "Travel": "travel",
    "Personal finance": "finance",
    "Fitness": "fitness",
    "Tech": "tech",
}

# Other ways people (or the CLI) might name the same niche.
ALIASES = {
    "food": "food", "restaurants": "food", "cooking": "food", "food & cooking": "food",
    "travel": "travel", "finance": "finance", "money": "finance", "personal finance": "finance",
    "fitness": "fitness", "gym": "fitness", "tech": "tech", "technology": "tech",
}


@dataclass(frozen=True)
class Playbook:
    name: str
    text: str
    banned_phrases: tuple[str, ...]
    editor_checks: str


def _section(text: str, title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return match.group(1).strip() if match else ""


@cache
def _load(key: str) -> Playbook:
    text = (HERE / f"{key}.md").read_text()
    name = text.splitlines()[0].lstrip("# ").strip()
    banned = tuple(line[2:].strip().lower() for line in _section(text, "Banned phrases").splitlines() if line.startswith("- "))
    return Playbook(name=name, text=text, banned_phrases=banned, editor_checks=_section(text, "Editor checks"))


def get_playbook(niche: str) -> Playbook | None:
    key = NICHES.get(niche) or ALIASES.get(niche.strip().lower())
    return _load(key) if key else None
