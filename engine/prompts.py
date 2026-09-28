"""All prompt text lives here so the craft rules can be read in one place.

RESEARCH looks up real-world facts when a topic needs them. DIRECTIONS decides
*what* the video is (the angle is the biggest single lever on quality). SCRIPT
decides *how it sounds*, with three competing hooks. REVIEW is the editor that
judges what code can't measure, and REVISION feeds every failure back.

Instructions hold the fixed text (stage prompt plus niche playbook) so the
provider can cache them; everything that changes per request goes in the input.
"""

import json

from .budget import HOOK_MAX_WORDS, Budget, requested_items
from .checks import BANNED_PHRASES, MAX_SENTENCE_WORDS
from .niches import get_playbook
from .schemas import Brief, Direction, DirectionSet, Fact, Issue, ResearchPlan, Script

# The first sentence of each tone doubles as the hint in the UI dropdown. The rest
# gives the writer concrete devices, plus one line showing the tone surviving an
# instructional format, which is where it was most often lost.
TONES = {
    "conversational": (
        "Like talking to a friend across the table. Contractions, the odd aside, sentences of mixed length. "
        "Give the reason before the instruction, and allow a small, true-to-the-topic admission. Warm, never salesy. "
        "In a tutorial it sounds like: \"Apps you opened once can still ask to track you, so switch that off while you're in there.\""
    ),
    "energetic": (
        "Fast and high-conviction. Mostly sentences under 8 words, strong verbs up front, no hedges like 'maybe' or 'kind of'. "
        "Each line hands off to the next with a consequence or a turn. "
        "In a tutorial it sounds like: \"Open Privacy. Kill tracking requests. Done. Now location.\""
    ),
    "calm expert": (
        "Measured and certain. Explains why things work, not just what to do. Authority comes from precise detail, not volume or hype words. "
        "In a tutorial it sounds like: \"Precise location is rarely needed. A weather app works just as well knowing your neighbourhood.\""
    ),
    "funny": (
        "Dry, observational humour that comes out of the topic itself: understatement, a well-placed specific, a deadpan turn. "
        "No puns for their own sake, no 'lol'. "
        "In a tutorial it sounds like: \"Your torch app does not need to know where you live. It's a torch.\""
    ),
    "storytelling": (
        "First person, starts inside a moment. Past tense, sensory detail, a small turn near the end that reframes what came before. "
        "Even advice arrives as what happened: \"I found out when a stranger replied to my photo with my street name.\""
    ),
    "blunt": (
        "No hedging, no softening, no apologising. States the uncomfortable thing in plain words, then backs it with a specific. "
        "Short verdicts. In a tutorial it sounds like: \"That setting helps advertisers, not you. Turn it off.\""
    ),
}

_CRAFT = f"""What makes a short-form script work:
- The hook earns the next three seconds. It opens a loop the viewer needs closed: a claim someone could disagree with, a stake, a mistake they are probably making, or a moment already in motion. A hook that just summarises the topic is the most common failure. It is one sentence of {HOOK_MAX_WORDS} words or fewer. No greetings, no "in this video", no throat-clearing.

  Weak -> strong (shape only; never reuse these):
  "Here are some tips for saving money." -> "I paid off $12,000 of debt by ignoring the advice everyone gives."
  "Let's talk about sourdough." -> "Most sourdough fails before you ever turn the oven on."
  "Paris has amazing views." -> "The best view of the Eiffel Tower is from a rooftop nobody queues for."

- The body delivers on exactly what the hook promised, with one idea, in order. Every beat carries at least one detail the viewer could not have predicted: an insider timing, a trade-off, a specific name or place, a counterintuitive consequence. Generic praise ("stunning", "great vibes", "something for everyone") is not a detail. Cut anything a viewer could have guessed.
- The last body line lands a payoff: the answer, the twist, or the takeaway, so the video feels finished. The payoff is concrete (a result, a number, a changed behaviour), not a moral like "consistency matters". Never end the body by recapping the points you just made; the viewer heard them ten seconds ago.
- One promise. Every item and every line serves the hook's single promise. For "N things" topics, choose a theme wide enough to hold N strong items (for three phone settings, "privacy" works; "delivery notifications" doesn't). If the theme can't hold N, widen it; never pad with an unrelated item. If the topic promises more items than the runtime fits, own it in the hook or first line ("My top 3, because you don't have 5 minutes").
- Why before what. In instructional formats, each step starts with what it saves the viewer from, then the instruction. That is the difference between a person talking and a manual.
- The close is exactly one ask that follows from this specific video and names something from it (a setting, a dish, a number): a pointed comment question, "save this for when...", "follow for part two where...". Never stack asks ("save this and comment"), never a generic "like and subscribe" or "check these".
- It is written for the ear: short sentences, contractions, "you", rhythm that varies. Nothing a person would not say out loud.
- Commit. Give a clear recommendation or verdict. A ranking ranks, and says why #1 beats the rest. Never dodge with "it depends", "no universal answer" or "ranked by what you're in the mood for". Opinions are welcome; invented facts are not.
- No meta-narration. Never explain the format or your approach ("quick rule", "here's how this works", "I'm matching each..."). The body delivers from its first word.
- Vary sentence shape. In a list, never introduce each item with the same structure.
- The tone is audible in every line, not just the hook. Instructional formats still carry it: a tutorial in a blunt tone sounds blunt, not like a manual. Someone hearing any single sentence should be able to name the tone.
- Be truthful about the world: never invent statistics, prices, studies or quotes; if you are unsure of a fact, use a concrete observable detail instead. In a first-person story, personal details (an amount, a day, a moment) are what make it real: use modest, plausible ones the creator can swap for their own."""


def _tone_line(tone: str) -> str:
    description = TONES.get(tone.lower())
    if not description:
        return tone
    return f"{tone}: {description} (The quoted lines show the feel only; never reuse their words or ideas.)"


def _brief_block(brief: Brief, budget: Budget) -> str:
    return (
        f"Niche: {brief.niche}\n"
        f"Topic: {brief.topic}\n"
        f"Runtime: {budget.seconds} seconds spoken (about {budget.total} words)\n"
        f"Tone: {_tone_line(brief.tone)}"
    )


DIRECTIONS_INSTRUCTIONS = f"""You are a short-form video strategist who has written thousands of TikToks, Reels and Shorts that people watch to the end.

A creator gives you a rough idea. Your job is to propose three directions for the video, so they can pick one before any script is written.

{_CRAFT}

Rules for the three directions:
- They must differ in angle, not just format. Give exactly one of each:
  1. Surprising: challenges what most people assume about this topic.
  2. Story: puts the viewer inside a specific moment or person's experience.
  3. Practical: the most useful, save-worthy version of the topic.
  If two directions would lead to broadly the same script, replace one. Label each with its kind.
- Each uses a different format. Draw from: ranked countdown, myth vs reality, "you're doing it wrong", POV or story, before and after, contrarian take, "things nobody tells you", mini tutorial, test or experiment, head-to-head comparison, confession or mistake.
- If the topic promises a number of items, every direction delivers exactly that many as a numbered list, and each angle must be wide enough to hold that many strong items. The directions differ in how the items are chosen and ordered, not in how many there are.
- Every direction answers the question the topic actually asks. If the topic asks for the best pizza in LA, every direction names pizzerias; a story or surprising angle is a way into that answer, never a replacement for it.
- Each has a real angle, a reason this take is worth watching over the thousand generic versions.
- The hook is the exact line the creator would say first, in the requested tone.
- The brief is exactly two sentences: how the video plays out, then what the viewer walks away with.
- The beats are the body's points in order, each naming the concrete detail it delivers. The runtime fits the number of beats you are told, no more.
- Recommend the direction most likely to be watched to the end and shared: the strongest hook and the most satisfying payoff. Usefulness alone is not the test, and Practical is not the default. Say why in one sentence."""


RESEARCH_PLAN_INSTRUCTIONS = """You decide whether a short-form video script needs web research before it's written.

Research is needed when a good script depends on real-world facts that could be wrong if guessed: specific places, restaurants and their dishes, products, app or phone settings, prices, opening details, events, or statistics.
Research is not needed for personal stories, opinions, or general advice that doesn't name specific real things.

If research is needed, write up to three short web searches that would find the most useful facts."""


def research_plan_input(brief: Brief) -> str:
    return f"Niche: {brief.niche}\nTopic: {brief.topic}"


RESEARCH_INSTRUCTIONS = """You research facts for a short-form video script. Search the web, then return five to ten concrete facts a creator could say on camera: names, signature items, what something does and where to find it, timing or logistics.

Rules:
- Every fact must come from a page you actually found, and its URL must be that page's exact URL.
- Facts, not opinions or rankings. The writer adds the opinion.
- Facts about the topic itself, never about the sources (not "this guide was updated in March").
- Prefer official sites and reputable, recent sources.
- One fact per item, in plain words, no markdown."""


def research_input(brief: Brief, plan: ResearchPlan) -> str:
    searches = "\n".join(f"- {q}" for q in plan.queries)
    return f"Niche: {brief.niche}\nTopic: {brief.topic}\n\nSuggested searches:\n{searches}"


def _list_block(brief: Brief) -> str:
    count = requested_items(brief.topic)
    if not count:
        return ""
    return (
        f"\nThe topic promises {count} items, so this is a numbered list of exactly {count}. "
        f"Say each number out loud at the start of its own paragraph (\"Number 1:\" ... \"Number {count}:\"). "
        f"For a ranking, count down so the best comes last. Don't cut or add items."
    )


def _facts_block(facts: list[Fact] | None) -> str:
    if not facts:
        return ""
    listed = "\n".join(f"- {f.claim}" for f in facts)
    return (
        "\n\nResearched facts. Use these for any real-world specific (a name, dish, setting, place detail, price). "
        "Don't state real-world specifics that aren't here. Opinions and rankings are still yours to make.\n"
        f"{listed}"
    )


def _playbook_block(brief: Brief, with_examples: bool = True) -> str:
    playbook = get_playbook(brief.niche)
    if not playbook:
        return ""
    text = playbook.text if with_examples else playbook.text.split("## Example scripts")[0].rstrip()
    return f"\n\nNiche playbook. Follow it closely; it defines what good means for this audience:\n\n{text}"


# Instructions = fixed stage prompt + fixed niche playbook, so every call for a
# niche starts with an identical prefix the provider can cache. Everything that
# changes per request goes in the input, after it.

def directions_instructions(brief: Brief) -> str:
    # Directions plan the video; the example scripts only matter to the writer.
    return DIRECTIONS_INSTRUCTIONS + _playbook_block(brief, with_examples=False)


def direction_repair_instructions(brief: Brief) -> str:
    return DIRECTION_REPAIR_INSTRUCTIONS + _playbook_block(brief, with_examples=False)


def script_instructions(brief: Brief) -> str:
    return SCRIPT_INSTRUCTIONS + _playbook_block(brief)


def review_instructions(brief: Brief) -> str:
    playbook = get_playbook(brief.niche)
    checks = f"\n\nNiche checks for {playbook.name}:\n{playbook.editor_checks}" if playbook else ""
    return REVIEW_INSTRUCTIONS + checks


def targeted_note(scope: frozenset[str]) -> str:
    parts = " and ".join({"hook": "the hook options", "cta": "the CTA"}[p] for p in sorted(scope))
    return f"Only rewrite {parts}. The body is final and stays exactly as it is, so make the new version fit it."


def directions_input(brief: Brief, budget: Budget, facts: list[Fact] | None = None, required_format: str | None = None) -> str:
    must = f"\nOne of the three directions must use this format: {required_format}." if required_format else ""
    return (
        f"{_brief_block(brief, budget)}\n"
        f"Beats per direction: {budget.beats}\n"
        f"Longest list that fits this runtime: {budget.max_items} items"
        f"{must}"
        f"{_list_block(brief)}"
        f"{_facts_block(facts)}\n\n"
        "Propose three directions."
    )


SCRIPT_INSTRUCTIONS = f"""You are a short-form video scriptwriter. You write words a creator will say straight to camera.

{_CRAFT}

Hard rules:
- Hit the word budgets you are given. The total must land within the stated range, because runtime depends on it. Count as you write.
- Hooks: write three competing options. Each is one sentence of {HOOK_MAX_WORDS} words or fewer, and each uses a different pattern from: a verdict someone could argue with, a mistake the viewer is making, a moment already in motion, a surprising specific (a number, a name, a detail), a question with a non-obvious answer. The chosen direction's hook can be one of them, tightened. An editor will pick the strongest, so make all three genuinely good and genuinely different.
- Never fall back on hook templates: "Pick the wrong X, and...", "X, ranked by...", "Stop doing X", "Here's why...", "Did you know...".
- Body: follow the beats in order. No sentence over {MAX_SENTENCE_WORDS} words; most well under 15.
- CTA: one clear, specific ask tied to this video.
- Layout: the body is read off a teleprompter, so give each beat or list item its own paragraph, with a blank line between paragraphs.
- Spoken words only: no emojis, hashtags, stage directions, brackets, headings, bullet points or "1." style lists. A spoken list says "Number 1:", "Number 2:" out loud. Numbers as digits are fine.
- Never use these phrases: {", ".join(f'"{p}"' for p in BANNED_PHRASES)}."""


def _direction_block(direction: Direction) -> str:
    beats = "\n".join(f"{i}. {beat}" for i, beat in enumerate(direction.beats, 1))
    return (
        f"Format: {direction.format}\n"
        f"Angle: {direction.angle}\n"
        f"Hook: {direction.hook}\n"
        f"Brief: {direction.brief}\n"
        f"Beats:\n{beats}"
    )


def _budget_block(budget: Budget) -> str:
    return (
        f"Word budgets: hook about {budget.hook}, body about {budget.body}, cta about {budget.cta}.\n"
        f"Total must be between {budget.total_min} and {budget.total_max} words (target {budget.total}).\n"
        f"Longest list that fits: {budget.max_items} items."
    )


def script_input(brief: Brief, budget: Budget, direction: Direction, facts: list[Fact] | None = None) -> str:
    return (
        f"{_brief_block(brief, budget)}\n\n"
        f"Chosen direction:\n{_direction_block(direction)}\n\n"
        f"{_budget_block(budget)}"
        f"{_list_block(brief)}"
        f"{_facts_block(facts)}\n\n"
        "Write the script."
    )


REVIEW_INSTRUCTIONS = """You are a tough short-form video editor reading a draft before it's filmed. You judge what code can't measure.

1. The hook. You get several options; pick the one a stranger scrolling fast would stop for, as long as the body pays it off. Score that one 1-5:
5 - they stop and need the next line: real tension, a stake, or a specific that sparks curiosity.
4 - strong and specific, with a clear reason to keep watching.
3 - clear but safe: it describes the topic, or is relatable but familiar.
2 - vague or generic; could open a video about almost anything in this niche.
1 - confusing, clickbait the body can't pay off, or a greeting.
Common failures: restating the topic, promising "tips" or "things" without a stake, a question with an obvious answer, hype words standing in for a specific.

2. The body. Does it deliver what the hook promises? Score it 1-5:
5 - every line carries a specific the viewer couldn't have guessed; nothing is said twice; it ends on a concrete payoff.
3 - solid but with filler: a generic line, a point made twice, an item that doesn't serve the hook's promise, an instruction read out like a manual, or an ending that recaps the list or states a moral.
1 - vague throughout.
Name the single biggest problem and quote the words.

3. The tone. Read it aloud in your head. Score 1-5 how clearly it sounds like the requested tone in every line, not just the opening. A script that sounds like a neutral guide when "energetic" or "funny" was asked for is a 2.

4. The close. Score the CTA 1-5: 5 is one natural ask that names something specific from this video; 3 is a generic ask ("check these", "let me know", "save this") that could end any video; 1 is missing or stacks several asks.

5. The facts. If researched facts are given, quote any real-world specific in the script (a name, dish, setting, place detail, price) that they don't support. Opinions and rankings are fine.

6. The niche. If you are given niche checks, answer each one honestly. Fail the script on any clear miss, but only for a problem you haven't already named for the body; never flag the same flaw twice.

Be honest. Most first drafts are a 3 on something."""


DIRECTION_REPAIR_INSTRUCTIONS = DIRECTIONS_INSTRUCTIONS + """

You are revising your own directions. Some hooks broke the hook rules. Return all three directions, changing only the hooks listed, and keep everything else as it was."""


def direction_repair_input(brief: Brief, budget: Budget, directions: DirectionSet, problems: list[str]) -> str:
    listed = "\n".join(f"- {p}" for p in problems)
    return (
        f"{directions_input(brief, budget)}\n\n"
        f"Your directions:\n{json.dumps(directions.model_dump(), indent=2)}\n\n"
        f"Hooks to fix:\n{listed}"
    )


def review_input(brief: Brief, hook_options: list[str], body: str, cta: str, facts: list[Fact] | None = None) -> str:
    hooks = "\n".join(f"{i}. {hook}" for i, hook in enumerate(hook_options))
    return (
        f"Niche: {brief.niche}\n"
        f"Requested tone: {_tone_line(brief.tone)}\n\n"
        f"Hook options (pick the strongest, judge the script with it):\n{hooks}\n\n"
        f"Body: {body}\n\n"
        f"CTA: {cta}"
        f"{_facts_block(facts)}"
    )


def revision_input(brief: Brief, budget: Budget, direction: Direction, draft: Script, issues: list[Issue], word_counts: dict, facts: list[Fact] | None = None) -> str:
    problems = "\n".join(f"- {issue.message}" for issue in issues)
    hook_flagged = any(i.code.startswith("hook") or i.code == "weak_hook" for i in issues)
    hook_note = (
        "The hook was flagged: write three fresh options."
        if hook_flagged
        else "The editor's chosen hook passed: keep it as the first option, and offer two new alternatives."
    )
    return (
        f"{_brief_block(brief, budget)}\n\n"
        f"Chosen direction:\n{_direction_block(direction)}\n\n"
        f"{_budget_block(budget)}"
        f"{_list_block(brief)}"
        f"{_facts_block(facts)}\n\n"
        f"Your previous draft:\n{json.dumps(draft.model_dump(), indent=2)}\n\n"
        f"Measured word counts: hook {word_counts['hook']}, body {word_counts['body']}, "
        f"cta {word_counts['cta']}, total {word_counts['total']}.\n\n"
        f"It failed these checks:\n{problems}\n\n"
        f"{hook_note}\n"
        "Rewrite the script to fix every problem. Keep what already works; do not flatten the voice."
    )
