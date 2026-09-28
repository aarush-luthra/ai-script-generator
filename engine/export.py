"""Serialise a pipeline run to JSON-ready dicts and readable Markdown."""

from dataclasses import asdict

from .checks import script_sections, script_stats
from .schemas import Script


def outcome_to_dict(outcome: dict, model: str | None = None) -> dict:
    result = outcome["result"]
    directions = outcome["directions"]
    return {
        "model": model,
        "input": asdict(outcome["brief"]),
        "budget": asdict(outcome["budget"]) | {"total_min": outcome["budget"].total_min, "total_max": outcome["budget"].total_max},
        "research": [f.model_dump() for f in outcome.get("facts", [])],
        "directions": [d.model_dump() for d in directions.directions],
        "chosen_index": directions.recommended_index,
        "recommendation_reason": directions.recommendation_reason,
        "output": result.script.model_dump(),
        "stats": script_stats(result.script),
        "review": result.review.model_dump() if result.review else None,
        "remaining_issues": [issue.message for issue in result.issues],
        "drafts": [
            {
                "script": d.script.model_dump(),
                "hook_options": d.hook_options,
                "review": d.review.model_dump() if d.review else None,
                "issues": [i.message for i in d.issues],
            }
            for d in result.drafts
        ],
    }


def _script_lines(script: Script) -> list[str]:
    lines = []
    for section in script_sections(script):
        lines += [f"**[{section['start']}–{section['end']}] {section['name']}**", ""]
        for line in section["lines"]:
            lines += [line, ""]
    return lines


def outcome_to_markdown(record: dict) -> str:
    inp, out, stats = record["input"], record["output"], record["stats"]
    words = stats["words"]
    lines = [
        f"# {inp['topic']}",
        "",
        f"**Niche:** {inp['niche']} · **Target:** {inp['target_seconds']}s · **Tone:** {inp['tone']}"
        + (f" · **Model:** {record['model']}" if record.get("model") else ""),
        "",
        "## Script",
        "",
        *_script_lines(Script(**out)),
        f"**Total:** {words['total']} words ≈ {stats['seconds']}s spoken "
        f"(target {record['budget']['total']} words / {inp['target_seconds']}s)",
        "",
        f"**Editor:** hook {record['review']['hook_score']}/5, tone {record['review']['tone_score']}/5 · " if record.get("review") else "",
        f"**Drafts:** {len(record['drafts'])} · **Remaining issues:** "
        + ("none" if not record["remaining_issues"] else "; ".join(record["remaining_issues"])),
        "",
        "## Directions considered",
        "",
    ]
    for i, d in enumerate(record["directions"]):
        marker = " ✅ chosen" if i == record["chosen_index"] else ""
        lines += [
            f"### {i + 1}. {d['format']}{marker}",
            "",
            f"- **Angle ({d['kind']}):** {d['angle']}",
            f"- **Hook:** {d['hook']}",
            f"- **Brief:** {d['brief']}",
            "",
        ]
    lines += [f"**Why chosen:** {record['recommendation_reason']}", ""]
    return "\n".join(lines)
