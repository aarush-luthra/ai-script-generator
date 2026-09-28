"""The generation pipeline: research, plan directions, write, check, revise.

    research()            ->  sourced facts, only when the topic depends on them
    propose_directions()  ->  three angles to choose from (the UI's cards)
    write_script()        ->  script for one chosen direction, checked and revised
    run() / generate()    ->  the whole thing hands-off; generate() returns {hook, body, cta}
"""

from collections.abc import Callable

from . import prompts
from .budget import Budget, make_budget, requested_items
from .checks import check_hook, check_script, script_stats
from .llm import LLM, LLMError, OpenAILLM
from .niches import get_playbook
from .schemas import (
    Brief,
    CtaRewrite,
    Direction,
    DirectionSet,
    Draft,
    Fact,
    FactSheet,
    HookCtaRewrite,
    HookRewrite,
    Issue,
    ResearchPlan,
    Review,
    Script,
    ScriptDraft,
    ScriptResult,
)

# Safety ceiling so a model that can't satisfy a check can't loop forever.
MAX_REVISIONS = 3

# Editor scores below this send the draft back for another pass.
MIN_SCORE = 4

# Issue codes that come from the editor's judgement rather than a measurement.
EDITOR_CODES = {"weak_hook", "no_payoff", "weak_body", "off_tone", "weak_cta", "unsupported_fact", "niche_miss"}

# Issues that only concern the hook or the close; these get targeted rewrites.
HOOK_CODES = {"hook_too_long", "hook_multi_sentence", "hook_weak_opener", "weak_hook"}
CTA_CODES = {"cta_missing", "cta_too_long", "weak_cta"}

# Stop revising an editor complaint once it has survived this many rewrites.
STALL_AFTER = 2

# Hidden reasoning effort per stage. Reasoning tokens dominate latency, so each
# stage gets the least that doesn't cost quality. Measured: directions lose
# nothing at "low" and the card-hook repair nothing at "none". Scripts at "low"
# miss word budgets and churn; rewrites at "low" are 2-3x faster per call but
# break length rules and add rounds, so net slower. The editor at "low" is
# less strict without being faster.
EFFORT = {"research_plan": "none", "research": "low", "directions": "low", "repair": "none", "script": "medium", "revision": "medium", "review": "medium"}


def research(brief: Brief, llm: LLM) -> list[Fact]:
    """Look up real-world facts before writing, when the topic depends on them.

    A quick call decides whether research is needed at all (a personal savings
    story doesn't; "best pizza in LA" does). Every fact must cite a page the search
    actually visited: facts whose URL the search never opened are dropped rather
    than trusted.
    """
    plan = llm.parse(
        prompts.RESEARCH_PLAN_INSTRUCTIONS, prompts.research_plan_input(brief), ResearchPlan,
        effort=EFFORT["research_plan"], stage="research_plan",
    )
    if not plan.needs_research:
        return []
    sheet, visited = llm.search(
        prompts.RESEARCH_INSTRUCTIONS, prompts.research_input(brief, plan), FactSheet, effort=EFFORT["research"]
    )
    return [
        Fact(claim=f.claim.replace("**", "").strip(), source_url=f.source_url)
        for f in sheet.facts
        if f.source_url in visited and f.claim.strip()
    ]


def propose_directions(
    brief: Brief, llm: LLM, budget: Budget | None = None, facts: list[Fact] | None = None, required_format: str | None = None
) -> DirectionSet:
    budget = budget or make_budget(brief.target_seconds)
    result = llm.parse(
        prompts.directions_instructions(brief),
        prompts.directions_input(brief, budget, facts, required_format),
        DirectionSet,
        effort=EFFORT["directions"],
        stage="directions",
    )
    if len(result.directions) != 3:
        raise LLMError(f"Expected 3 directions, got {len(result.directions)}.")
    if not 0 <= result.recommended_index < 3:
        result.recommended_index = 0

    # Fix rule-breaking hooks here, before a writer builds a whole script on one.
    problems = [
        f'Direction {i + 1} hook "{d.hook}": {issue.message}'
        for i, d in enumerate(result.directions)
        for issue in check_hook(d.hook)
    ]
    if problems:
        repaired = llm.parse(
            prompts.direction_repair_instructions(brief),
            prompts.direction_repair_input(brief, budget, result, problems),
            DirectionSet,
            effort=EFFORT["repair"],
        stage="repair",
        )
        if len(repaired.directions) == 3:
            for original, fixed in zip(result.directions, repaired.directions):
                if not check_hook(fixed.hook):
                    original.hook = fixed.hook
    return result


def review_script(brief: Brief, hook_options: list[str], body: str, cta: str, llm: LLM, facts: list[Fact] | None = None) -> tuple[Review, list[Issue]]:
    """The judgements code can't make: which hook is strongest, does the body pay it off, do tone and close land?"""
    review = llm.parse(prompts.review_instructions(brief), prompts.review_input(brief, hook_options, body, cta, facts), Review, effort=EFFORT["review"], stage="review")
    issues = []
    if review.hook_score < MIN_SCORE:
        issues.append(Issue("weak_hook", f"An editor scored the hook {review.hook_score}/5: {review.hook_problem} Fix: {review.hook_fix}"))
    if not review.body_pays_off:
        issues.append(Issue("no_payoff", "The body doesn't concretely deliver what the hook promises. End on a specific result, not a moral."))
    if review.body_score < MIN_SCORE:
        issues.append(Issue("weak_body", f"An editor scored the body {review.body_score}/5: {review.body_problem}"))
    if review.tone_score < MIN_SCORE:
        issues.append(Issue("off_tone", f"An editor scored the {brief.tone} tone {review.tone_score}/5. Fix: {review.tone_fix}"))
    if facts and review.unsupported_claim.strip().lower() not in ("", "none"):
        issues.append(Issue("unsupported_fact", f"Not backed by the research: {review.unsupported_claim} Use a researched fact or make it an opinion."))
    if review.cta_score < MIN_SCORE:
        issues.append(Issue("weak_cta", f"An editor scored the CTA {review.cta_score}/5. Fix: {review.cta_fix}"))
    if not review.niche_pass:
        issues.append(Issue("niche_miss", f"Fails the {brief.niche} playbook: {review.niche_problem}"))
    return review, issues


def _assess(brief: Brief, draft: ScriptDraft, budget: Budget, llm: LLM, facts: list[Fact] | None = None) -> Draft:
    """Hook shootout, then checks: rule-breaking hooks are dropped in code, the editor picks from the rest."""
    options = [h.strip() for h in draft.hook_options if h.strip()] or [""]
    valid = [h for h in options if not check_hook(h)] or options
    review, review_issues = review_script(brief, valid, draft.body, draft.cta, llm, facts)
    script = Script(hook=valid[min(max(review.best_hook, 0), len(valid) - 1)], body=draft.body, cta=draft.cta)
    playbook = get_playbook(brief.niche)
    banned = playbook.banned_phrases if playbook else ()
    return Draft(script, check_script(script, budget, banned, requested_items(brief.topic)) + review_issues, review, valid)


def _no_progress(drafts: list[Draft]) -> bool:
    """The last rewrite didn't reduce the editor's complaints, and nothing measurable is left.

    Profiled runs showed rewrites that trade one judgement-call complaint for
    another at ~40s a round. When a rewrite doesn't improve on the best draft so
    far, another one rarely does either.
    """
    if len(drafts) < 2:
        return False
    last = drafts[-1]
    if any(i.code not in EDITOR_CODES for i in last.issues):
        return False  # a measured failure (length, hook rules...) is always worth fixing
    best_before = min(len(d.issues) for d in drafts[:-1])
    return len(last.issues) >= best_before


def _stalled(drafts: list[Draft]) -> set[str]:
    """Editor complaints that survived STALL_AFTER rewrites unchanged.

    Measured runs showed a stuck judgement (usually tone) doesn't move on the
    3rd or 4th attempt, so we stop spending time on it. Rule failures measured
    in code are never treated as stalled: those always get every retry.
    """
    recent = drafts[-(STALL_AFTER + 1):]
    if len(recent) <= STALL_AFTER:
        return set()
    persistent = set.intersection(*({i.code for i in d.issues} for d in recent))
    return persistent & EDITOR_CODES


def _draft_event(n: int, draft: Draft) -> dict:
    stats = script_stats(draft.script)
    return {
        "type": "draft_checked",
        "draft": n,
        "script": draft.script.model_dump(),  # lets the page show a draft while it's being improved
        "words": stats["words"]["total"],
        "seconds": stats["seconds"],
        "review": draft.review.model_dump() if draft.review else None,
        "issues": [{"code": i.code, "message": i.message} for i in draft.issues],
    }


def _written_event(n: int, draft: ScriptDraft, budget: Budget, brief: Brief) -> dict:
    """The writer's output before the editor has seen it, so the page can show it right away."""
    hook = next((h for h in draft.hook_options if h.strip() and not check_hook(h)), draft.hook_options[0] if draft.hook_options else "")
    script = Script(hook=hook, body=draft.body, cta=draft.cta)
    playbook = get_playbook(brief.niche)
    measured = check_script(script, budget, playbook.banned_phrases if playbook else (), requested_items(brief.topic))
    stats = script_stats(script)
    return {
        "type": "draft_written",
        "draft": n,
        "script": script.model_dump(),
        "words": stats["words"]["total"],
        "seconds": stats["seconds"],
        "issues": [{"code": i.code, "message": i.message} for i in measured],
    }


def _rewrite_scope(issues: list[Issue]) -> frozenset[str] | None:
    """Which parts a revision must touch, or None for a full rewrite.

    Output tokens drive latency, so when only the hook or the close was flagged
    we ask for just that part and keep the body as it is.
    """
    codes = {i.code for i in issues}
    if not codes or not codes <= HOOK_CODES | CTA_CODES:
        return None
    return frozenset({"hook"} if codes & HOOK_CODES else set()) | frozenset({"cta"} if codes & CTA_CODES else set())


_TARGETED_SCHEMAS = {
    frozenset({"hook"}): HookRewrite,
    frozenset({"cta"}): CtaRewrite,
    frozenset({"hook", "cta"}): HookCtaRewrite,
}


def _revise(
    brief: Brief, budget: Budget, direction: Direction, last: Draft, llm: LLM, scope: frozenset[str] | None, facts: list[Fact] | None
) -> ScriptDraft:
    revision = prompts.revision_input(brief, budget, direction, last.script, last.issues, script_stats(last.script)["words"], facts)
    if scope is None:
        return llm.parse(prompts.script_instructions(brief), revision, ScriptDraft, effort=EFFORT["revision"], stage="revision")

    patch = llm.parse(
        prompts.script_instructions(brief),
        revision + "\n" + prompts.targeted_note(scope),
        _TARGETED_SCHEMAS[scope],
        effort=EFFORT["revision"],
        stage="revision",
    )
    return ScriptDraft(
        hook_options=patch.hook_options if "hook" in scope else [last.script.hook],
        body=last.script.body,
        cta=patch.cta if "cta" in scope else last.script.cta,
    )


def write_script(
    brief: Brief,
    direction: Direction,
    llm: LLM,
    budget: Budget | None = None,
    on_progress: Callable[[dict], None] | None = None,
    facts: list[Fact] | None = None,
    max_revisions: int = MAX_REVISIONS,
) -> ScriptResult:
    budget = budget or make_budget(brief.target_seconds)
    emit = on_progress or (lambda event: None)

    emit({"type": "draft_started", "draft": 1, "fixing": [], "scope": "full"})
    script = llm.parse(
        prompts.script_instructions(brief),
        prompts.script_input(brief, budget, direction, facts),
        ScriptDraft,
        effort=EFFORT["script"],
        stage="script",
    )
    emit(_written_event(1, script, budget, brief))
    drafts = [_assess(brief, script, budget, llm, facts)]
    emit(_draft_event(1, drafts[0]))

    while drafts[-1].issues and len(drafts) <= max_revisions:
        last = drafts[-1]
        stalled = _stalled(drafts)
        if stalled and all(i.code in stalled for i in last.issues):
            emit({"type": "stalled", "codes": sorted(stalled)})
            break
        if _no_progress(drafts):
            emit({"type": "stalled", "codes": sorted({i.code for i in last.issues})})
            break
        scope = _rewrite_scope(last.issues)
        emit({
            "type": "draft_started",
            "draft": len(drafts) + 1,
            "fixing": sorted({i.code for i in last.issues}),
            "scope": "full" if scope is None else "+".join(sorted(scope)),
        })
        script = _revise(brief, budget, direction, last, llm, scope, facts)
        emit(_written_event(len(drafts) + 1, script, budget, brief))
        drafts.append(_assess(brief, script, budget, llm, facts))
        emit(_draft_event(len(drafts), drafts[-1]))

    # Fewest remaining issues wins; on a tie, prefer the later (more revised) draft.
    best = min(reversed(drafts), key=lambda d: len(d.issues))
    return ScriptResult(script=best.script, issues=best.issues, drafts=drafts, review=best.review)


def _pick_direction(directions: DirectionSet, required_format: str | None) -> int:
    """The recommended direction, unless a specific format was asked for and one matches."""
    if required_format:
        keyword = required_format.split()[0].lower()
        for i, d in enumerate(directions.directions):
            if keyword in d.format.lower():
                return i
    return directions.recommended_index


def run(brief: Brief, llm: LLM | None = None, required_format: str | None = None) -> dict:
    """Hands-off run that keeps every intermediate step, for samples and debugging.

    required_format stands in for a user clicking a particular card: the
    directions step must offer that format, and it's the one written.
    """
    llm = llm or OpenAILLM()
    budget = make_budget(brief.target_seconds)
    facts = research(brief, llm)
    directions = propose_directions(brief, llm, budget, facts, required_format)
    directions.recommended_index = _pick_direction(directions, required_format)
    chosen = directions.directions[directions.recommended_index]
    result = write_script(brief, chosen, llm, budget, facts=facts)
    return {
        "brief": brief,
        "budget": budget,
        "facts": facts,
        "directions": directions,
        "result": result,
    }


def generate(niche: str, topic: str, target_seconds: int, tone: str = "conversational", llm: LLM | None = None) -> dict:
    """The assignment's interface: idea in, {hook, body, cta} out."""
    outcome = run(Brief(niche, topic, target_seconds, tone), llm)
    return outcome["result"].script.model_dump()
