"""Pipeline tests with a scripted fake LLM: no network, no API key."""

import pytest

from engine.llm import LLMError
from engine.pipeline import MAX_REVISIONS, generate, propose_directions, research, write_script
from engine.pipeline import run as pl_run
from engine.schemas import (
    Brief, CtaRewrite, Direction, DirectionSet, Fact, FactSheet, HookCtaRewrite, HookRewrite, ResearchPlan, Review, Script, ScriptDraft,
)

BRIEF = Brief("travel", "best beaches in Dubai", 30, "energetic")

DIRECTION = Direction(
    kind="Practical",
    format="Ranked countdown",
    angle="Ranks by crowd level, not looks.",
    hook="Dubai's best beach is the one nobody posts.",
    brief="Counts down three beaches. You leave knowing where to go at 7am.",
    beats=["beach three", "beach two"],
)

GOOD = ScriptDraft(
    hook_options=["Dubai's best beach is the one nobody posts.", "Most tourists pick the loudest beach.", "I found the quiet beach at 7am."],
    body=" ".join(["Short clear sentence here with some detail."] * 9),  # 63 words
    cta="Comment which one you'd pick.",
)
NO_RESEARCH = ResearchPlan(needs_research=False, queries=[])
BAD = ScriptDraft(hook_options=["Hey guys, let's dive in!"], body="Too short.", cta="")


def as_script(draft: ScriptDraft, hook: int = 0) -> Script:
    return Script(hook=draft.hook_options[hook], body=draft.body, cta=draft.cta)

STRONG = Review(best_hook=0, hook_score=5, hook_problem="none", hook_fix="none", body_pays_off=True, body_score=5, body_problem="none", tone_score=5, tone_fix="none", cta_score=5, cta_fix="none", unsupported_claim="none", niche_pass=True, niche_problem="none")
SAFE = STRONG.model_copy(update={"hook_score": 3, "hook_problem": "It summarises the topic.", "hook_fix": "Lead with the crowd-free beach."})


class FakeLLM:
    """Returns queued responses per schema, and records every call."""

    def __init__(self, **queues):
        self.queues = {name: list(items) for name, items in queues.items()}
        self.calls = []

    def parse(self, instructions, input, schema, effort=None, stage=None):
        self.calls.append((schema, input, instructions))
        return self.queues[schema.__name__].pop(0)

    def inputs(self, schema):
        return [call[1] for call in self.calls if call[0] is schema]

    def search(self, instructions, input, schema, effort=None):
        self.calls.append((schema, input, instructions))
        return self.queues[schema.__name__].pop(0), set(self.queues.get("visited", [set()])[0])

    def instructions(self, schema):
        return [call[2] for call in self.calls if call[0] is schema]


def test_clean_first_draft_needs_no_revision():
    llm = FakeLLM(ScriptDraft=[GOOD], Review=[STRONG])
    result = write_script(BRIEF, DIRECTION, llm)
    assert result.issues == []
    assert len(result.drafts) == 1
    assert result.review.hook_score == 5


def test_failed_checks_are_fed_back_into_revision():
    llm = FakeLLM(ScriptDraft=[BAD, GOOD], Review=[STRONG, STRONG])
    result = write_script(BRIEF, DIRECTION, llm)
    assert result.script == as_script(GOOD)
    revision_prompt = llm.inputs(ScriptDraft)[1]
    assert "failed these checks" in revision_prompt
    assert "let's dive in" in revision_prompt


def test_weak_hook_gets_a_targeted_rewrite_that_keeps_the_body():
    new_hooks = HookRewrite(hook_options=["Dubai's calmest beach opens at 6am.", "Tourists skip the one beach locals use.", "I found the quiet beach at 7am."])
    llm = FakeLLM(ScriptDraft=[GOOD], HookRewrite=[new_hooks], Review=[SAFE, STRONG])
    result = write_script(BRIEF, DIRECTION, llm)
    assert len(result.drafts) == 2 and result.issues == []
    assert result.script.hook == new_hooks.hook_options[0]
    assert result.script.body == GOOD.body
    assert "Lead with the crowd-free beach." in llm.inputs(HookRewrite)[0]
    assert "Only rewrite the hook options" in llm.inputs(HookRewrite)[0]


def test_missing_payoff_is_an_issue():
    no_payoff = STRONG.model_copy(update={"body_pays_off": False})
    llm = FakeLLM(ScriptDraft=[GOOD] * (MAX_REVISIONS + 1), Review=[no_payoff] * (MAX_REVISIONS + 1))
    result = write_script(BRIEF, DIRECTION, llm)
    assert {i.code for i in result.issues} == {"no_payoff"}


def test_off_tone_triggers_revision_with_editor_feedback():
    flat = STRONG.model_copy(update={"tone_score": 2, "tone_fix": "Shorter sentences, more punch."})
    llm = FakeLLM(ScriptDraft=[GOOD, GOOD], Review=[flat, STRONG])
    result = write_script(BRIEF, DIRECTION, llm)
    assert len(result.drafts) == 2
    assert "Shorter sentences, more punch." in llm.inputs(ScriptDraft)[1]


def test_revisions_stop_at_ceiling_and_keep_best_draft():
    llm = FakeLLM(ScriptDraft=[BAD] * (MAX_REVISIONS + 1), Review=[SAFE] * (MAX_REVISIONS + 1))
    result = write_script(BRIEF, DIRECTION, llm)
    assert len(result.drafts) == MAX_REVISIONS + 1
    assert result.issues


def test_generate_returns_assignment_shape_using_recommended_direction():
    other = DIRECTION.model_copy(update={"format": "POV story"})
    directions = DirectionSet(directions=[other, DIRECTION, other], recommended_index=1, recommendation_reason="x")
    llm = FakeLLM(ResearchPlan=[NO_RESEARCH], DirectionSet=[directions], ScriptDraft=[GOOD], Review=[STRONG])
    out = generate("travel", "best beaches in Dubai", 30, llm=llm)
    assert set(out) == {"hook", "body", "cta"}
    assert "Ranked countdown" in llm.inputs(ScriptDraft)[0]


def test_wrong_number_of_directions_is_an_error():
    llm = FakeLLM(ResearchPlan=[NO_RESEARCH], DirectionSet=[DirectionSet(directions=[DIRECTION], recommended_index=0, recommendation_reason="x")])
    with pytest.raises(LLMError):
        generate("travel", "best beaches in Dubai", 30, llm=llm)


def test_weak_body_triggers_revision():
    recap = STRONG.model_copy(update={"body_score": 3, "body_problem": 'Ends by recapping: "that\'s your shortlist".'})
    llm = FakeLLM(ScriptDraft=[GOOD, GOOD], Review=[recap, STRONG])
    write_script(BRIEF, DIRECTION, llm)
    assert "that's your shortlist" in llm.inputs(ScriptDraft)[1]


def test_rule_breaking_card_hooks_are_repaired_before_writing():
    two_sentences = DIRECTION.model_copy(update={"hook": "Want sun? Read this."})
    fixed = DIRECTION.model_copy(update={"hook": "Dubai's quietest beach is the one tourists skip."})
    broken = DirectionSet(directions=[two_sentences, DIRECTION, DIRECTION], recommended_index=0, recommendation_reason="x")
    repaired = DirectionSet(directions=[fixed, DIRECTION, DIRECTION], recommended_index=0, recommendation_reason="x")
    llm = FakeLLM(DirectionSet=[broken, repaired])
    result = propose_directions(BRIEF, llm)
    assert result.directions[0].hook == fixed.hook
    assert "single sentence" in llm.inputs(DirectionSet)[1]


def test_clean_card_hooks_need_no_repair():
    llm = FakeLLM(DirectionSet=[DirectionSet(directions=[DIRECTION] * 3, recommended_index=0, recommendation_reason="x")])
    propose_directions(BRIEF, llm)
    assert len(llm.calls) == 1


def test_stuck_editor_complaint_stops_after_one_unproductive_rewrite():
    flat = STRONG.model_copy(update={"tone_score": 2, "tone_fix": "More punch."})
    llm = FakeLLM(ScriptDraft=[GOOD] * 2, Review=[flat] * 2)
    events = []
    result = write_script(BRIEF, DIRECTION, llm, on_progress=events.append)
    assert len(result.drafts) == 2  # the rewrite didn't help, so don't try again
    assert events[-1] == {"type": "stalled", "codes": ["off_tone"]}


def test_measured_failures_are_never_treated_as_stalled():
    llm = FakeLLM(ScriptDraft=[BAD] * (MAX_REVISIONS + 1), Review=[STRONG] * (MAX_REVISIONS + 1))
    result = write_script(BRIEF, DIRECTION, llm)
    assert len(result.drafts) == MAX_REVISIONS + 1


def test_progress_events_trace_each_draft():
    llm = FakeLLM(ScriptDraft=[BAD, GOOD], Review=[STRONG, STRONG])
    events = []
    write_script(BRIEF, DIRECTION, llm, on_progress=events.append)
    assert [e["type"] for e in events] == [
        "draft_started", "draft_written", "draft_checked",
        "draft_started", "draft_written", "draft_checked",
    ]
    assert "hook_weak_opener" in events[3]["fixing"]
    assert events[5]["issues"] == []


def test_niche_miss_triggers_revision_with_playbook_feedback():
    miss = STRONG.model_copy(update={"niche_pass": False, "niche_problem": 'No dish to order: "Tacos 1986 is for tacos".'})
    food = Brief("Food & restaurants", "top restaurants in LA", 30, "conversational")
    llm = FakeLLM(ScriptDraft=[GOOD, GOOD], Review=[miss, STRONG])
    write_script(food, DIRECTION, llm)
    assert "No dish to order" in llm.inputs(ScriptDraft)[1]


def test_playbook_reaches_every_prompt_for_known_niche():
    food = Brief("Food & restaurants", "top restaurants in LA", 30, "conversational")
    directions = DirectionSet(directions=[DIRECTION] * 3, recommended_index=0, recommendation_reason="x")
    llm = FakeLLM(DirectionSet=[directions], ScriptDraft=[GOOD], Review=[STRONG])
    write_script(food, propose_directions(food, llm).directions[0], llm)
    dir_in, script_in, review_in = (llm.instructions(s)[0] for s in (DirectionSet, ScriptDraft, Review))
    assert "What counts as a specific" in dir_in and "What counts as a specific" in script_in
    assert "Does every item tell the viewer what to order or do?" in review_in


def test_editor_picks_the_hook_from_the_shootout():
    pick_third = STRONG.model_copy(update={"best_hook": 2})
    llm = FakeLLM(ScriptDraft=[GOOD], Review=[pick_third])
    result = write_script(BRIEF, DIRECTION, llm)
    assert result.script.hook == "I found the quiet beach at 7am."
    assert "2. I found the quiet beach at 7am." in llm.inputs(Review)[0]


def test_rule_breaking_hook_options_never_reach_the_editor():
    draft = GOOD.model_copy(update={"hook_options": ["Hey guys, welcome back to my channel.", "Most tourists pick the loudest beach."]})
    llm = FakeLLM(ScriptDraft=[draft], Review=[STRONG])
    result = write_script(BRIEF, DIRECTION, llm)
    assert result.script.hook == "Most tourists pick the loudest beach."
    assert "welcome back" not in llm.inputs(Review)[0]
    assert result.drafts[0].hook_options == ["Most tourists pick the loudest beach."]


def test_out_of_range_pick_falls_back_safely():
    llm = FakeLLM(ScriptDraft=[GOOD], Review=[STRONG.model_copy(update={"best_hook": 7})])
    assert write_script(BRIEF, DIRECTION, llm).script.hook == GOOD.hook_options[2]


def test_passing_hook_is_kept_on_revision():
    long_body = GOOD.model_copy(update={"body": " ".join(["Short clear sentence here with some detail."] * 14)})
    llm = FakeLLM(ScriptDraft=[long_body, GOOD], Review=[STRONG, STRONG])
    write_script(BRIEF, DIRECTION, llm)
    assert "keep it as the first option" in llm.inputs(ScriptDraft)[1]


def test_generic_cta_gets_a_targeted_rewrite_that_keeps_hook_and_body():
    generic = STRONG.model_copy(update={"cta_score": 3, "cta_fix": "Ask which beach they'd pick at 7am."})
    llm = FakeLLM(ScriptDraft=[GOOD], CtaRewrite=[CtaRewrite(cta="Which beach are you hitting at 7am?")], Review=[generic, STRONG])
    result = write_script(BRIEF, DIRECTION, llm)
    assert result.script == Script(hook=GOOD.hook_options[0], body=GOOD.body, cta="Which beach are you hitting at 7am?")
    assert "Ask which beach they'd pick at 7am." in llm.inputs(CtaRewrite)[0]
    assert "2. " not in llm.inputs(Review)[1]  # only the kept hook is offered


def test_hook_and_cta_issues_share_one_targeted_rewrite():
    both = SAFE.model_copy(update={"cta_score": 2, "cta_fix": "Name a beach."})
    patch = HookCtaRewrite(hook_options=["Tourists skip the one beach locals use."], cta="Which beach wins?")
    llm = FakeLLM(ScriptDraft=[GOOD], HookCtaRewrite=[patch], Review=[both, STRONG])
    result = write_script(BRIEF, DIRECTION, llm)
    assert (result.script.hook, result.script.body, result.script.cta) == (patch.hook_options[0], GOOD.body, patch.cta)


def test_body_issues_still_get_a_full_rewrite():
    events = []
    recap = STRONG.model_copy(update={"body_score": 3, "body_problem": "Recaps."})
    llm = FakeLLM(ScriptDraft=[GOOD, GOOD], Review=[recap, STRONG])
    write_script(BRIEF, DIRECTION, llm, on_progress=events.append)
    assert events[3]["scope"] == "full"


def test_draft_events_carry_the_script_for_early_preview():
    events = []
    write_script(BRIEF, DIRECTION, FakeLLM(ScriptDraft=[GOOD], Review=[STRONG]), on_progress=events.append)
    written, checked = events[1], events[2]
    assert written["type"] == "draft_written" and written["script"] == as_script(GOOD).model_dump()
    assert checked["script"] == as_script(GOOD).model_dump()


def test_writer_is_told_the_list_limit():
    llm = FakeLLM(ScriptDraft=[GOOD], Review=[STRONG])
    write_script(BRIEF, DIRECTION, llm)
    assert "Longest list that fits: 3 items." in llm.inputs(ScriptDraft)[0]


def test_rewrite_that_makes_no_progress_ends_the_loop():
    one_issue = STRONG.model_copy(update={"tone_score": 3, "tone_fix": "Warmer."})
    other_issue = STRONG.model_copy(update={"body_score": 3, "body_problem": "Generic line."})
    llm = FakeLLM(ScriptDraft=[GOOD, GOOD], Review=[one_issue, other_issue])
    events = []
    result = write_script(BRIEF, DIRECTION, llm, on_progress=events.append)
    assert len(result.drafts) == 2  # traded one complaint for another: stop, don't loop
    assert events[-1]["type"] == "stalled"


def test_progress_keeps_the_loop_going():
    two = STRONG.model_copy(update={"tone_score": 3, "tone_fix": "Warmer.", "body_score": 3, "body_problem": "Generic."})
    one = STRONG.model_copy(update={"tone_score": 3, "tone_fix": "Warmer."})
    llm = FakeLLM(ScriptDraft=[GOOD, GOOD, GOOD], Review=[two, one, STRONG])
    assert len(write_script(BRIEF, DIRECTION, llm).drafts) == 3


# ---------- research ----------

PIZZA = Brief("Food & restaurants", "best pizza in LA", 30, "conversational")
REAL = "https://www.pizzeriamozza.com/los-angeles-menu/"


def test_personal_story_skips_the_web_search():
    llm = FakeLLM(ResearchPlan=[NO_RESEARCH])
    assert research(Brief("Personal finance", "I automated my savings", 60, "storytelling"), llm) == []
    assert [c[0] for c in llm.calls] == [ResearchPlan]


def test_facts_citing_pages_the_search_never_visited_are_dropped():
    sheet = FactSheet(facts=[
        Fact(claim="Pizzeria Mozza's **fennel sausage** pie has panna and red onion.", source_url=REAL),
        Fact(claim="D-Town serves Detroit-style squares.", source_url="https://made-up.example/d-town"),
    ])
    llm = FakeLLM(ResearchPlan=[ResearchPlan(needs_research=True, queries=["best pizza LA"])], FactSheet=[sheet], visited=[{REAL}])
    facts = research(PIZZA, llm)
    assert facts == [Fact(claim="Pizzeria Mozza's fennel sausage pie has panna and red onion.", source_url=REAL)]


def test_facts_reach_directions_writer_and_editor():
    facts = [Fact(claim="Pizzeria Mozza's fennel sausage pie has panna and red onion.", source_url=REAL)]
    directions = DirectionSet(directions=[DIRECTION] * 3, recommended_index=0, recommendation_reason="x")
    llm = FakeLLM(DirectionSet=[directions], ScriptDraft=[GOOD], Review=[STRONG])
    write_script(PIZZA, propose_directions(PIZZA, llm, facts=facts).directions[0], llm, facts=facts)
    for schema in (DirectionSet, ScriptDraft, Review):
        assert "fennel sausage pie" in llm.inputs(schema)[0]


def test_unsupported_claim_triggers_a_rewrite():
    facts = [Fact(claim="Pizzeria Mozza's fennel sausage pie has panna and red onion.", source_url=REAL)]
    made_up = STRONG.model_copy(update={"unsupported_claim": '"D-Town\'s Detroit pepperoni"'})
    llm = FakeLLM(ScriptDraft=[GOOD, GOOD], Review=[made_up, STRONG])
    write_script(PIZZA, DIRECTION, llm, facts=facts)
    assert "Not backed by the research" in llm.inputs(ScriptDraft)[1]


def test_unsupported_claim_is_ignored_without_research():
    made_up = STRONG.model_copy(update={"unsupported_claim": "something"})
    llm = FakeLLM(ScriptDraft=[GOOD], Review=[made_up])
    assert write_script(BRIEF, DIRECTION, llm).issues == []


def test_rewrite_ceiling_can_be_lowered_for_cheap_testing():
    llm = FakeLLM(ScriptDraft=[BAD, BAD], Review=[STRONG, STRONG])
    assert len(write_script(BRIEF, DIRECTION, llm, max_revisions=1).drafts) == 2


# ---------- sample controls ----------

def test_required_format_is_requested_and_chosen():
    confession = DIRECTION.model_copy(update={"kind": "Story", "format": "Confession or mistake"})
    directions = DirectionSet(directions=[DIRECTION, DIRECTION, confession], recommended_index=0, recommendation_reason="x")
    llm = FakeLLM(ResearchPlan=[NO_RESEARCH], DirectionSet=[directions], ScriptDraft=[GOOD], Review=[STRONG])
    outcome = pl_run(BRIEF, llm, required_format="confession or mistake")
    assert "must use this format: confession or mistake" in llm.inputs(DirectionSet)[0]
    assert outcome["directions"].recommended_index == 2


def test_list_topics_tell_every_step_the_exact_count():
    tech = Brief("Tech", "three iPhone settings you should turn off right now", 30, "conversational")
    directions = DirectionSet(directions=[DIRECTION] * 3, recommended_index=0, recommendation_reason="x")
    llm = FakeLLM(DirectionSet=[directions], ScriptDraft=[GOOD, GOOD, GOOD, GOOD], Review=[STRONG] * 4)
    result = write_script(tech, propose_directions(tech, llm).directions[0], llm)
    assert "exactly 3" in llm.inputs(DirectionSet)[0] and "exactly 3" in llm.inputs(ScriptDraft)[0]
    assert "list_count" in {i.code for i in result.issues}  # GOOD never counts to 3, so it's flagged every round
