"""Generate a short-form video script from the command line.

    python cli.py --niche travel --topic "best beaches in Dubai" --seconds 45
    python cli.py ... --auto      # let the model pick the direction
    python cli.py ... --json      # print the full run as JSON
"""

import argparse
import json
import sys

from engine.budget import make_budget
from engine.checks import script_stats
from engine.llm import LLMError, OpenAILLM
from engine.pipeline import propose_directions, research, write_script
from engine.prompts import TONES
from engine.schemas import Brief


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Turn an idea into a short-form video script.")
    parser.add_argument("--niche", required=True)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--seconds", type=int, default=45)
    parser.add_argument("--tone", default="conversational", help=f"One of {', '.join(TONES)}, or free text.")
    parser.add_argument("--auto", action="store_true", help="Use the model's recommended direction.")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON.")
    return parser.parse_args()


def choose(directions, auto: bool) -> int:
    rec = directions.recommended_index
    for i, d in enumerate(directions.directions):
        tag = "  (recommended)" if i == rec else ""
        print(f"\n[{i + 1}] {d.format}{tag}\n    Angle: {d.angle}\n    Hook:  {d.hook}\n    {d.brief}")
    print(f"\nWhy recommended: {directions.recommendation_reason}")
    if auto or not sys.stdin.isatty():
        return rec
    answer = input(f"\nPick a direction [1-3, enter for {rec + 1}]: ").strip()
    return int(answer) - 1 if answer in {"1", "2", "3"} else rec


def main() -> int:
    args = parse_args()
    brief = Brief(args.niche, args.topic, args.seconds, args.tone)
    try:
        budget = make_budget(brief.target_seconds)
        llm = OpenAILLM()
        print(f"Target: {budget.seconds}s ≈ {budget.total} words. Researching...", file=sys.stderr)
        facts = research(brief, llm)
        print(f"{len(facts)} sourced facts. Finding directions...", file=sys.stderr)
        directions = propose_directions(brief, llm, budget, facts)
        index = choose(directions, args.auto or args.json)
        print("\nWriting script...", file=sys.stderr)
        result = write_script(brief, directions.directions[index], llm, budget, facts=facts)
    except (LLMError, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    stats = script_stats(result.script)
    if args.json:
        print(json.dumps({**result.script.model_dump(), "stats": stats}, indent=2))
        return 0

    words = stats["words"]
    print(f"\nHOOK ({words['hook']} words)\n{result.script.hook}")
    print(f"\nBODY ({words['body']} words)\n{result.script.body}")
    print(f"\nCTA ({words['cta']} words)\n{result.script.cta}")
    hook_score = f" · hook {result.review.hook_score}/5, tone {result.review.tone_score}/5" if result.review else ""
    print(f"\n{words['total']} words ≈ {stats['seconds']}s (target {budget.seconds}s){hook_score} · {len(result.drafts)} draft(s)")
    for issue in result.issues:
        print(f"  ! {issue.message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
