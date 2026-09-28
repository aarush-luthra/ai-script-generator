"""Deterministic checks on a drafted script.

Anything we can measure, we measure in code instead of trusting the model's
self-assessment: length, hook size, cliches, and text that can't be spoken.
Each failure becomes a concrete instruction in the revision prompt.
"""

import re

from .budget import HOOK_MAX_WORDS, WORDS_PER_SECOND, Budget, seconds_for
from .schemas import Issue, Script

MAX_SENTENCE_WORDS = 25

# Phrases that mark a script as generic, AI-written, or padded.
BANNED_PHRASES = [
    "let's dive in",
    "dive into",
    "deep dive",
    "delve",
    "game-changer",
    "game changer",
    "unlock",
    "unleash",
    "elevate",
    "embark",
    "hidden gem",
    "look no further",
    "without further ado",
    "buckle up",
    "stay tuned",
    "ever wondered",
    "in today's video",
    "in this video",
    "like and subscribe",
    "smash that",
    "don't forget to",
    "whether you're a",
    "at the end of the day",
    "it's no secret",
    "a must-see",
    "a must-visit",
    "breathtaking",
    "crystal clear",
    "crystal-clear",
    "nestled",
    "bustling",
    "something for everyone",
]

# Ways a hook wastes its first second.
BANNED_HOOK_OPENERS = [
    "hey guys",
    "hey everyone",
    "hi everyone",
    "hello everyone",
    "welcome back",
    "what's up",
    "today we",
    "today i",
    "so,",
    "in this",
]

_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF\U0000FE0F]"
)
_HASHTAG = re.compile(r"(?<!\w)#[^\W\d]\w*")  # "#19" is a menu number, not a hashtag
_STAGE_DIRECTION = re.compile(r"\[[^\]]*\]|\((?:pause|beat|cut|b-roll|music|on screen|text)[^)]*\)", re.I)
_MARKDOWN = re.compile(r"\*\*|__|^\s*[-*•]\s|^\s*#+\s|^\s*\d+[.)]\s", re.M)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def count_words(text: str) -> int:
    return sum(1 for token in text.split() if any(ch.isalnum() for ch in token))


def sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_SPLIT.split(text.strip()) if count_words(s) > 0]


def script_stats(script: Script) -> dict:
    words = {
        "hook": count_words(script.hook),
        "body": count_words(script.body),
        "cta": count_words(script.cta),
    }
    words["total"] = sum(words.values())
    return {"words": words, "seconds": seconds_for(words["total"])}


_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_SPOKEN_NUMBER = re.compile(r"\bnumber\s+(\d+|" + "|".join(_NUMBER_WORDS) + r")\b", re.I)


def counted_items(body: str) -> set[int]:
    """The list numbers the body says out loud ("Number 3", "number two")."""
    found = set()
    for match in _SPOKEN_NUMBER.finditer(body):
        token = match.group(1).lower()
        found.add(int(token) if token.isdigit() else _NUMBER_WORDS[token])
    return found


_ITEM_START = re.compile(r"(?<=[.!?])\s+(?=Number\s+(?:\d+|" + "|".join(_NUMBER_WORDS) + r")\b)", re.I)


def paragraphs(text: str) -> list[str]:
    """Script lines as a creator reads them: one beat per paragraph, each "Number N" item on its own."""
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        out.extend(part.strip() for part in _ITEM_START.split(block.replace("\n", " ")) if part.strip())
    return out


def timecode(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def script_sections(script: Script) -> list[dict]:
    """Hook, body and CTA with start and end timecodes from the speaking rate."""
    sections, elapsed = [], 0.0
    for name, text in (("HOOK", script.hook), ("BODY", script.body), ("CTA", script.cta)):
        duration = count_words(text) / WORDS_PER_SECOND
        sections.append({"name": name, "start": timecode(elapsed), "end": timecode(elapsed + duration), "lines": paragraphs(text)})
        elapsed += duration
    return sections


def check_script(
    script: Script, budget: Budget, extra_banned: tuple[str, ...] = (), required_items: int | None = None
) -> list[Issue]:
    issues: list[Issue] = []
    stats = script_stats(script)["words"]

    total = stats["total"]
    if total > budget.total_max:
        issues.append(Issue(
            "too_long",
            f"Script is {total} words; the {budget.seconds}s target allows at most {budget.total_max}. "
            f"Cut about {total - budget.total} words, mostly from the body.",
        ))
    elif total < budget.total_min:
        issues.append(Issue(
            "too_short",
            f"Script is {total} words; the {budget.seconds}s target needs at least {budget.total_min}. "
            f"Add about {budget.total - total} words of concrete detail to the body.",
        ))

    issues.extend(check_hook(script.hook))

    if stats["cta"] == 0:
        issues.append(Issue("cta_missing", "The CTA is empty."))
    elif stats["cta"] > budget.cta + 8:
        issues.append(Issue(
            "cta_too_long",
            f"CTA is {stats['cta']} words; keep it near {budget.cta}. One clear ask.",
        ))

    for part in ("hook", "body", "cta"):
        issues.extend(_check_speakable(part, getattr(script, part)))

    if required_items:
        counted = counted_items(script.body)
        if counted != set(range(1, required_items + 1)):
            said = ", ".join(f"Number {n}" for n in sorted(counted)) or "none"
            issues.append(Issue(
                "list_count",
                f"The topic promises {required_items} items, so the body must count exactly Number 1 to Number {required_items} out loud, "
                f"each as its own paragraph. It currently says: {said}.",
            ))

    for sentence in sentences(script.body):
        n = count_words(sentence)
        if n > MAX_SENTENCE_WORDS:
            issues.append(Issue(
                "long_sentence",
                f"This body sentence is {n} words, too long to say in one breath; split it: \"{sentence}\"",
            ))

    full_text = " ".join([script.hook, script.body, script.cta]).lower().replace("’", "'")
    for phrase in (*BANNED_PHRASES, *extra_banned):
        if re.search(rf"\b{re.escape(phrase)}\b", full_text):
            issues.append(Issue("banned_phrase", f"Remove the cliche \"{phrase}\" and say something specific instead."))

    return issues


def check_hook(hook: str) -> list[Issue]:
    issues = []
    n = count_words(hook)
    if n > HOOK_MAX_WORDS:
        issues.append(Issue("hook_too_long", f"Hook is {n} words; it must be {HOOK_MAX_WORDS} or fewer to land in ~3 seconds."))
    if len(sentences(hook)) > 1:
        issues.append(Issue("hook_multi_sentence", "Hook must be a single sentence."))
    lowered = hook.lower().lstrip()
    for opener in BANNED_HOOK_OPENERS:
        if lowered.startswith(opener):
            issues.append(Issue("hook_weak_opener", f"Hook opens with \"{opener}\"; start on the claim, number or tension itself."))
    return issues


def _check_speakable(part: str, text: str) -> list[Issue]:
    issues = []
    if _EMOJI.search(text):
        issues.append(Issue("emoji", f"Remove emojis from the {part}; this is spoken text."))
    if _HASHTAG.search(text):
        issues.append(Issue("hashtag", f"Remove hashtags from the {part}."))
    if _STAGE_DIRECTION.search(text):
        issues.append(Issue("stage_direction", f"Remove stage directions or bracketed notes from the {part}; only words the creator says."))
    if _MARKDOWN.search(text):
        issues.append(Issue("formatting", f"Remove bullets, numbering or markdown from the {part}; write it as speech."))
    return issues
