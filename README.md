# AI Script Generator

Turn a rough idea into a short-form video script (hook, body, call-to-action) timed to the runtime a creator wants to film.

```python
>>> from engine import generate
>>> generate(niche="Personal finance", topic="why your pay rise disappears within three months", target_seconds=45)
{"hook": "...", "body": "...", "cta": "..."}
```

It comes with a web app: type an idea, pick one of three directions, and edit the finished script with live timing and checks.

---

## Quick start

Needs Python 3.11+ and an OpenAI API key.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # then put your key in .env
```

**Web app** (the main way to use it):

```bash
.venv/bin/uvicorn app.main:app --reload
```

Open http://localhost:8000. Type an idea, choose length, niche and tone, pick a direction card, and edit the script. "View sample prompts and scripts" under the chat box shows the saved samples.

**Command line:**

```bash
.venv/bin/python cli.py --niche Travel --topic "best beaches in Dubai" --seconds 30 --tone energetic
```

Add `--auto` to let it pick the direction, or `--json` for machine-readable output.

**Samples and tests:**

```bash
.venv/bin/python make_samples.py            # regenerate every sample into samples/
.venv/bin/python make_samples.py --only 2   # regenerate one
.venv/bin/python -m pytest                  # 90 tests, no API key or network needed
```

**Settings** (`.env`):

| Variable | Default | What it does |
|---|---|---|
| `OPENAI_API_KEY` | none | Required |
| `OPENAI_MODEL` | `gpt-6-luna` | Model for every stage |
| `OPENAI_WRITER_MODEL` | same as above | Lets the writing stage use a different model |
| `MAX_REVISIONS` | `3` | Rewrites per script in the web app. `1` makes testing cheaper; samples always use the full loop |

A script costs about $0.02–0.05 on `gpt-6-luna`, including web research.

---

## The approach

Most script generators are one prompt: "write a 45-second script about X", then you take whatever comes back. Script Bench treats writing as a process with a check at every step. It is built around one principle: **measure what can be measured in code, and use a separate model as an editor for the judgements that can't.**

```
 idea + niche + length + tone
            │
   1. Research (only if the topic needs real facts) ──► sourced fact sheet
            │
   2. Directions ──► three different angles (Surprising / Story / Practical)
            │           the user picks one; ★ = the model's recommendation
   3. Write ──► body + CTA + three competing hooks
            │
   4. Check ──► code: length, hook rules, clichés, breath length, list count…
            │    editor: picks the best hook, scores hook, body, tone, CTA,
            │            niche checks, and flags anything the research doesn't back up
            │
   5. Revise ──► every failure goes back as a specific instruction
            │    (only the hook or CTA is rewritten when only they failed)
            ▼
   finished script, timed to the second
```

### 1. Research, when the topic needs it
A quick first call decides whether the script depends on real-world facts. "Top 5 pizzas in LA" does; "why your pay rise disappears" doesn't. If it does, one web search builds a fact sheet of 5–10 facts, each with its source page. **Any fact whose source the search never actually opened is thrown away.** The writer must use the fact sheet for real-world specifics (opinions are still its own), and the editor flags anything unsupported. The sources appear next to the script so a creator can check them before filming.

### 2. Directions before words
The angle decides more of a script's quality than any sentence in it, so that decision comes first, while it's cheap to change. The model proposes three directions that differ in angle, not just format: one **surprising**, one **story**, one **practical**. Each card shows the format, the hook, the angle and a two-sentence brief. If the topic promises a number ("three iPhone settings"), every direction delivers exactly that many.

### 3. Writing with a word budget
Runtime is maths, not a request. At 2.5 spoken words per second, 30/45/60 seconds becomes about 75/112/150 words, split between hook (≤15 words, landing in about 3 seconds), body and CTA. The writer gets the budget, the niche playbook (below), the facts and the chosen direction, and drafts **three hooks in different patterns** (a verdict, a mistake the viewer is making, a moment in motion, a surprising specific) for the editor to choose from.

### 4. Two kinds of checks
- **In code** (`engine/checks.py`): total length within ±10%, hook of one sentence and ≤15 words with no greeting, 32 banned clichés plus 6–10 more per niche, no sentence too long to say in one breath, spoken words only (no emojis, hashtags or stage directions), one short CTA, and the right number of items for list topics. These are exact and free, and never skipped.
- **By an editor model** (`REVIEW` in `engine/prompts.py`): which of the three hooks a fast scroller would stop for, whether the body pays it off with specifics, whether the requested tone is audible in every line, whether the CTA is specific to this video, the niche's own checks, and any claim the research doesn't support.

### 5. Revision that knows when to stop
Every failure goes back to the writer as an instruction ("the analytics setting breaks the location theme"), not "try again". If only the hook or the CTA failed, only that part is rewritten. The loop stops when everything passes, when a rewrite doesn't reduce the editor's complaints, or after three rewrites. It then returns the draft with the fewest problems and lists what's left unresolved rather than hiding it.

### Niche playbooks
"Be specific" means different things in different niches. Each of the five niches (Food & restaurants, Travel, Personal finance, Fitness, Tech) has a playbook in `engine/niches/`. It covers who's watching, **what counts as a real specific** (the dish to order and how; the amount to automate and when), formats that work and list sizes that fit, hooks, niche clichés, pitfalls, closes, the editor's niche checks, and two hand-written example scripts that pass every rule themselves (a test enforces this).

---

## Why it produces good scripts

What I think makes a short-form script good, and the part of the system that enforces each quality:

| A good script… | How the generator gets there |
|---|---|
| **earns the next three seconds** with tension, a stake or a specific, not a summary of the topic | Three competing hooks in different patterns; code rejects long, multi-sentence or greeting hooks; the editor picks the one a stranger would stop for and scores it |
| **delivers one idea with specifics the viewer couldn't have guessed** | The niche playbook defines what a specific is; the editor names generic lines and quotes them; "one promise" rule: every item serves the hook |
| **commits** to a verdict or ranking with a reason | Prompt rules against "it depends"; rankings must say why #1 wins; opinions are encouraged, invented facts are not |
| **ends on a payoff**, not a recap or a moral | Explicit rule, plus an editor check that fails recap endings |
| **closes with one ask** tied to this video | Code limits CTA length; the editor scores specificity; stacked asks are banned |
| **sounds like a person talking** in the chosen tone | Each tone has concrete techniques and an example line; the editor scores tone on every line; sentences must fit one breath |
| **fits the runtime** | Word budget from the speaking rate, checked in code, shown live with timecodes |
| **is true** | Web research with verified sources; the editor flags unsupported claims; no invented statistics, prices or quotes |

### Decisions I measured instead of guessing
While building this I A/B tested settings, grading final scripts with a separate, stricter judge that didn't know which setting produced them:

- **Reasoning effort per stage.** Directions at low effort: 3× faster, same quality. Scripts at low effort: missed word budgets and churned through rewrites, so they stay at medium. The editor at low effort: less strict and *not* faster. Rewrites at low effort: 2–3× faster per call, but they broke length rules and added rounds. Details are in the comment on `EFFORT` in `engine/pipeline.py`.
- **Hook shootout.** Hook scores went from 3/5 in four of the five niches to 4/5 in all five. Before it, the model kept reusing one template ("Pick the wrong X, and…").
- **Niche playbooks.** The LA restaurants script went from "Tacos 1986 is the move when you want tacos" to the dish to order at each place ("the adobada, shaved off the trompo") with a committed #1.
- **Model choice.** `gpt-5-mini` as the writer was slower at medium effort and never passed the editor at low effort, so the writer stays on `gpt-6-luna`.
- **Stopping rules.** Profiling showed rewrites trading one editor complaint for another at about 40s a round, and a narrow theme that could never hold "three" settings. Hence: themes must fit the promised count, the editor can't flag the same flaw twice, and the loop stops when a rewrite doesn't improve anything.

### Speed
A finished script takes about 30 seconds to 3 minutes, mostly spent on editor-driven rewrites. The web app hides most of that: it starts writing the ★ direction while you read the cards, shows each draft as soon as it's written (locked while it's improved), and streams live progress ("Draft 2: rewriting the CTA").

---

## Samples

`samples/` holds one run per niche across all three runtimes, saved **exactly as generated**. Each has a readable `.md` and a `.json` with the full record: the research, all three directions, every draft and the editor's verdicts. The web app shows them under "View sample prompts and scripts". Two samples name the direction a user would have clicked (ranked countdown for the pizza list, confession for fitness). The rest use the recommended one. Anything the editor still flagged is listed, not hidden.

---

## Limitations

- **Tone ceiling.** "Energetic" on list-style content stays around 3/5 whatever the prompt says. I think that's the model tier; `OPENAI_WRITER_MODEL` exists to test a stronger writer.
- **Research reduces factual errors but doesn't remove them.** In testing, the model once credited a real pizza to the wrong restaurant even with the right source in hand. That's why facts are tied to sources and shown to the creator rather than trusted blindly.
- **Some scripts end with issues left.** When the loop stops, the best draft can still carry an editor complaint. It's shown next to the script.
- **Five niches are tuned.** Other niches work through the generic rules, but without a playbook the specifics are weaker.

---

## Project layout

```
engine/            the generator, usable without the web app
  pipeline.py      research → directions → write → check → revise
  prompts.py       every prompt, in one readable place
  checks.py        rules measured in code, plus script layout and timecodes
  budget.py        runtime → word budgets; how many items a topic promises
  niches/          one playbook per niche (Markdown), loaded into the prompts
  llm.py           the only file that talks to OpenAI (swap providers here)
  schemas.py       structured outputs (Pydantic)
  export.py        samples as JSON and Markdown
app/               FastAPI server + a single-page front end (no build step)
  jobs.py          background script jobs with a live, replayable event stream
cli.py             command-line version
make_samples.py    regenerates samples/
tests/             90 tests with a fake model: no API key, no network
NOTE.md            what makes a script good, and how the generator gets there
TODO.md            what's next (editor features, quality)
```
