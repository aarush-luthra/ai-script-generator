# TODO

## Editor mode
- [x] **Live timing meter per section**: word count, seconds and timecodes for hook, body and CTA, plus a runtime bar against the target range.
- [x] **Live rule checks** while editing (length, hook rules, clichés, breath length, spoken-words-only, CTA, numbered list), re-run in code on every edit, no AI cost.
- [ ] **Regenerate one section**: "give me 3 more hooks", keeping the body. The targeted-rewrite machinery (`HookRewrite`, `CtaRewrite`) already exists in the pipeline.
- [ ] **Use this draft**: stop the improvement loop and edit the current draft straight away.
- [ ] **Tighten / Expand**: rewrite one section to fit its word budget.
- [ ] **Read-aloud preview**: teleprompter that scrolls at speaking pace.

## Quality
- [ ] Energetic tone on list content is stuck at 3/5 in every measured round. Try a stronger writer model (`OPENAI_WRITER_MODEL`).
- [ ] Word-by-word streaming of drafts, if users click a card within ~10 seconds of the cards appearing.

## Out of scope
- Version history, collaboration, export formats.
