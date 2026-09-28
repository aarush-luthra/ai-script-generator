# What makes a script good

A short-form script has one job: keep a stranger watching until the end, then leave them with something worth acting on. To me, that breaks down into five things.

**1. The hook earns the next three seconds.** It opens a loop: a claim someone could argue with, a mistake the viewer is probably making, a moment already in motion. The most common failure is a hook that just summarises the topic ("Three Dubai beaches, ranked…"). That's clear, but it gives no reason to stay.

**2. The body pays off with specifics the viewer couldn't have guessed.** "Tacos 1986 is great for tacos" is filler. "Order the adobada, shaved off the trompo" is a reason to have watched. What counts as a specific changes by niche: a dish and how to order it, an amount and when to move it, a setting and what it costs you.

**3. It commits.** A ranking ranks and says why #1 wins. "It depends what you're in the mood for" is the model's safe default, and it kills a video. Opinions are welcome; invented facts aren't.

**4. It sounds like a person, in the chosen tone, at the right length.** Short sentences you can say in one breath, a tone audible in every line (not just the opening), and a runtime that fits the video the creator actually wants to film.

**5. It ends on a payoff and one ask.** Not a recap of what the viewer heard ten seconds ago, and not "like and subscribe". One ask that names something from this video.

## How the generator gets there

The principle is **measure what code can measure, and use a separate editor for the judgements it can't.** Runtime becomes a word budget (2.5 words per second), and length, hook rules, clichés, sentence length and list counts are all checked in code. A second model plays the editor: it picks the strongest of three competing hooks and scores the body, tone and CTA against the rules above. Every failure goes back to the writer as a specific instruction. The angle is chosen before any words are written, because it matters more than any sentence. Each niche has a playbook defining what a real specific is, and topics that depend on real-world facts get web research with verified sources.

I didn't guess at settings: I A/B tested them against a separate, stricter judge. That's how I know the hook shootout moved hooks from 3/5 to 4/5, and the playbooks turned vague lists into orderable ones.

## Where it still falls short

The editor is the same model tier as the writer, so it shares some blind spots. The iPhone sample passed every check yet argues for keeping a setting *on* in a video about settings to turn off. High-energy tone is the hardest thing to get from a small model. And research reduces factual errors without eliminating them, which is why the sources sit next to the script for the creator to check.
