from engine.budget import make_budget
from engine.checks import check_script, count_words
from engine.schemas import Script

BUDGET = make_budget(30)  # 75 words, 68-82 allowed


def words(n: int) -> str:
    return " ".join(["word"] * n)


def body_of(n: int) -> str:
    """n words, in sentences short enough to pass the breath check."""
    chunks = [words(10) + "." for _ in range(n // 10)]
    if n % 10:
        chunks.append(words(n % 10) + ".")
    return " ".join(chunks)


def make(hook="Most people waste their first paycheck in a week.", body=None, cta="Save this for payday."):
    hook_words, cta_words = count_words(hook), count_words(cta)
    return Script(hook=hook, body=body or body_of(75 - hook_words - cta_words), cta=cta)


def codes(script: Script) -> set[str]:
    return {issue.code for issue in check_script(script, BUDGET)}


def test_clean_script_passes():
    assert codes(make()) == set()


def test_count_words_ignores_punctuation_tokens():
    assert count_words("Wait — it's $5, really?") == 4


def test_too_long_and_too_short():
    assert "too_long" in codes(make(body=body_of(100)))
    assert "too_short" in codes(make(body=body_of(20)))


def test_hook_rules():
    assert "hook_too_long" in codes(make(hook=words(16) + "."))
    assert "hook_multi_sentence" in codes(make(hook="Stop. Read this."))
    assert "hook_weak_opener" in codes(make(hook="Hey guys, here is a money tip."))


def test_long_sentence_flagged():
    assert "long_sentence" in codes(make(body=words(30) + ". " + body_of(30)))


def test_banned_phrase_flagged_case_insensitive():
    assert "banned_phrase" in codes(make(cta="Like and Subscribe for more."))


def test_banned_phrases_match_whole_words_only():
    issues = check_script(make(cta="Let’s dive into the settings."), BUDGET)
    assert [i.message for i in issues if i.code == "banned_phrase"] == [
        'Remove the cliche "dive into" and say something specific instead.'
    ]


def test_unspeakable_text_flagged():
    assert "emoji" in codes(make(cta="Save this for payday 💸"))
    assert "hashtag" in codes(make(cta="Save this #money"))
    assert "hashtag" not in codes(make(cta="Order the #19 at Langer's."))
    assert "stage_direction" in codes(make(cta="[point at camera] Save this."))
    assert "formatting" in codes(make(body="- first point\n- second point"))


def test_empty_cta_flagged():
    assert "cta_missing" in codes(make(cta=""))


def test_numbered_list_must_count_every_item_out_loud():
    from engine.checks import counted_items
    body = "Number 3: tracking.\n\nNumber two: analytics.\n\n" + body_of(55)
    assert counted_items(body) == {2, 3}
    missing = check_script(make(body=body), BUDGET, required_items=3)
    assert "list_count" in {i.code for i in missing}
    assert "Number 2, Number 3" in next(i.message for i in missing if i.code == "list_count")
    full = "Number 3: tracking.\n\nNumber 2: analytics.\n\nNumber 1: location.\n\n" + body_of(52)
    assert "list_count" not in {i.code for i in check_script(make(body=full), BUDGET, required_items=3)}


def test_spoken_numbers_are_not_flagged_as_markdown_lists():
    body = "Number 1: tracking.\n\n" + body_of(60)
    assert "formatting" not in codes(make(body=body))


def test_script_layout_puts_each_numbered_item_on_its_own_line():
    from engine.checks import paragraphs, script_sections
    body = "Quick context first. Number 3: tracking. Number 2: analytics.\n\nNumber 1: location."
    assert paragraphs(body) == ["Quick context first.", "Number 3: tracking.", "Number 2: analytics.", "Number 1: location."]
    sections = script_sections(Script(hook=words(10), body=words(50), cta=words(5)))
    assert [(s["name"], s["start"], s["end"]) for s in sections] == [("HOOK", "0:00", "0:04"), ("BODY", "0:04", "0:24"), ("CTA", "0:24", "0:26")]
