"""Data shapes shared by the engine, the CLI and the web app.

The LLM-facing models (Direction, DirectionSet, Script) are passed to the
OpenAI SDK as structured-output schemas, so every field carries a description
the model can read.
"""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class Brief:
    niche: str
    topic: str
    target_seconds: int
    tone: str = "conversational"


class ResearchPlan(BaseModel):
    needs_research: bool = Field(description="True if a good script depends on real-world facts: specific places, products, menu items, settings, prices, events or statistics.")
    queries: list[str] = Field(description="Up to three web searches that would find those facts. Empty if no research is needed.")


class Fact(BaseModel):
    claim: str = Field(description="One concrete, checkable fact, useful in a short video: a name, a signature item, what something does, where or when.")
    source_url: str = Field(description="The exact URL of the page you found this fact on.")


class FactSheet(BaseModel):
    facts: list[Fact] = Field(description="Five to ten facts, each backed by a page you actually found.")


class Direction(BaseModel):
    kind: Literal["Surprising", "Story", "Practical"] = Field(description="Which of the three angle types this direction is.")
    format: str = Field(description="Short name of the video format, e.g. 'Ranked countdown', 'Myth vs reality', 'POV story'.")
    angle: str = Field(description="One sentence: what makes this take specific or surprising.")
    hook: str = Field(description="The exact first line the creator says on camera.")
    brief: str = Field(description="Exactly two sentences: how the video plays out and what the viewer walks away with.")
    beats: list[str] = Field(description="The body's points in order. Each beat names the concrete detail it delivers.")


class DirectionSet(BaseModel):
    directions: list[Direction] = Field(description="Exactly three directions, each a genuinely different format.")
    recommended_index: int = Field(description="0-based index of the direction most likely to hold viewers to the end.")
    recommendation_reason: str = Field(description="One sentence on why that direction is strongest for this niche and topic.")


class Script(BaseModel):
    hook: str = Field(description="One spoken sentence.")
    body: str = Field(description="The spoken body, as plain paragraphs.")
    cta: str = Field(description="The closing call-to-action, one or two spoken sentences.")


class ScriptDraft(BaseModel):
    """What the writer returns: three competing hooks; the editor picks one."""
    hook_options: list[str] = Field(description="Exactly three hooks, each one sentence, each using a different hook pattern.")
    body: str = Field(description="The spoken body, as plain paragraphs.")
    cta: str = Field(description="The closing call-to-action, one or two spoken sentences.")


class HookRewrite(BaseModel):
    """Targeted revision: only the hooks were flagged, so only hooks come back."""
    hook_options: list[str] = Field(description="Exactly three new hooks, each one sentence, each using a different hook pattern.")


class CtaRewrite(BaseModel):
    """Targeted revision: only the close was flagged."""
    cta: str = Field(description="The new call-to-action, one or two spoken sentences.")


class HookCtaRewrite(BaseModel):
    """Targeted revision: hook and close flagged, body is final."""
    hook_options: list[str] = Field(description="Exactly three new hooks, each one sentence, each using a different hook pattern.")
    cta: str = Field(description="The new call-to-action, one or two spoken sentences.")


class Review(BaseModel):
    best_hook: int = Field(description="0-based index of the strongest hook option. Score hook_score for that one.")
    hook_score: int = Field(description="1-5: would a stranger scrolling at speed stop for this line? 5 = must hear the next line, 3 = clear but safe, 1 = generic.")
    hook_problem: str = Field(description="One sentence naming the hook's biggest weakness, or 'none'.")
    hook_fix: str = Field(description="One sentence of concrete direction for a stronger hook. Not a full rewrite.")
    body_pays_off: bool = Field(description="True if the body clearly and concretely delivers what the hook promises.")
    body_score: int = Field(description="1-5: every line specific and non-obvious, nothing repeated, ends on a concrete payoff rather than a recap or moral.")
    body_problem: str = Field(description="One sentence naming the body's biggest weakness, quoting the offending words, or 'none'.")
    tone_score: int = Field(description="1-5: how clearly every line sounds like the requested tone.")
    tone_fix: str = Field(description="One sentence on what would make the tone land, or 'none'.")
    cta_score: int = Field(description="1-5: one natural ask that names something specific from this video.")
    cta_fix: str = Field(description="One sentence on how to make the CTA specific to this video, or 'none'.")
    unsupported_claim: str = Field(description="If researched facts were given: quote any real-world specific in the script they don't support. Otherwise 'none'.")
    niche_pass: bool = Field(description="True if the script passes every niche editor check you were given (true if none were given).")
    niche_problem: str = Field(description="One sentence naming the biggest niche-check failure, quoting the words, or 'none'.")


@dataclass(frozen=True)
class Issue:
    code: str
    message: str


@dataclass
class Draft:
    script: Script
    issues: list[Issue]
    review: Review | None = None
    hook_options: list[str] = field(default_factory=list)


@dataclass
class ScriptResult:
    script: Script
    issues: list[Issue]
    drafts: list[Draft] = field(default_factory=list)
    review: Review | None = None
