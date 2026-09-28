"""Turn a target runtime into word budgets.

Timing is arithmetic, not something we ask the model to guess. Conversational
short-form delivery runs at roughly 150 words per minute (2.5 words/sec), so
the runtime fixes the word count, and the word count is split across sections.
"""

import re
from dataclasses import dataclass

WORDS_PER_SECOND = 2.5

# A hook has to land in the first ~3-4 seconds, whatever the runtime.
HOOK_MAX_WORDS = 15
HOOK_MIN_WORDS = 6
HOOK_SHARE = 0.12

CTA_MIN_WORDS = 6
CTA_MAX_WORDS = 15
CTA_SHARE = 0.10

# How far the total may drift from target before we ask for a rewrite.
TOLERANCE = 0.10


@dataclass(frozen=True)
class Budget:
    seconds: int
    total: int
    hook: int
    body: int
    cta: int

    @property
    def total_min(self) -> int:
        return round(self.total * (1 - TOLERANCE))

    @property
    def total_max(self) -> int:
        return round(self.total * (1 + TOLERANCE))

    @property
    def max_items(self) -> int:
        """Longest list that fits: about one item per 10 seconds, 2 to 5 items."""
        return max(2, min(5, self.seconds // 10))

    @property
    def beats(self) -> int:
        """How many distinct points the body has room for."""
        if self.seconds <= 30:
            return 2
        if self.seconds <= 45:
            return 3
        return 4


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def make_budget(seconds: int) -> Budget:
    if not 10 <= seconds <= 180:
        raise ValueError(f"target_seconds must be between 10 and 180, got {seconds}")

    total = round(seconds * WORDS_PER_SECOND)
    hook = _clamp(round(total * HOOK_SHARE), HOOK_MIN_WORDS, HOOK_MAX_WORDS)
    cta = _clamp(round(total * CTA_SHARE), CTA_MIN_WORDS, CTA_MAX_WORDS)
    return Budget(seconds=seconds, total=total, hook=hook, body=total - hook - cta, cta=cta)


NUMBER_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_TIME_UNITS = {"seconds", "minutes", "hours", "days", "weeks", "months", "years", "times", "sessions"}
_COUNT = re.compile(r"\b(\d+|" + "|".join(NUMBER_WORDS) + r")\b((?:\s+[a-z'&-]+){0,2}?)\s+([a-z-]+s)\b")


def requested_items(topic: str) -> int | None:
    """How many items the topic promises ("three iPhone settings", "top 5 pizzas"), if any.

    Durations ("two years", "three months") aren't lists, so they don't count.
    """
    for match in _COUNT.finditer(topic.lower()):
        number, noun = match.group(1), match.group(3)
        if noun in _TIME_UNITS:
            continue
        count = int(number) if number.isdigit() else NUMBER_WORDS[number]
        if 2 <= count <= 10:
            return count
    return None


def seconds_for(words: int) -> float:
    return round(words / WORDS_PER_SECOND, 1)
