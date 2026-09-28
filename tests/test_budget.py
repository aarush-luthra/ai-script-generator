import pytest

from engine.budget import HOOK_MAX_WORDS, make_budget, seconds_for


@pytest.mark.parametrize("seconds, total", [(30, 75), (45, 112), (60, 150)])
def test_total_follows_speaking_rate(seconds, total):
    assert make_budget(seconds).total == total


@pytest.mark.parametrize("seconds", [15, 30, 45, 60, 90, 180])
def test_sections_sum_to_total(seconds):
    b = make_budget(seconds)
    assert b.hook + b.body + b.cta == b.total


def test_hook_is_capped_for_long_videos():
    assert make_budget(180).hook == HOOK_MAX_WORDS


def test_beats_scale_with_runtime():
    assert [make_budget(s).beats for s in (30, 45, 60)] == [2, 3, 4]


def test_tolerance_window():
    b = make_budget(60)
    assert (b.total_min, b.total_max) == (135, 165)


@pytest.mark.parametrize("seconds", [5, 500])
def test_rejects_unreasonable_runtimes(seconds):
    with pytest.raises(ValueError):
        make_budget(seconds)


def test_seconds_for():
    assert seconds_for(112) == 44.8


@pytest.mark.parametrize("topic, count", [
    ("three iPhone settings you should turn off right now", 3),
    ("top 5 pizzas in LA", 5),
    ("5 beaches in Dubai worth the drive", 5),
    ("I automated my savings and forgot about it for two years", None),
    ("why your pay rise disappears within three months", None),
    ("best pizza in LA", None),
])
def test_requested_items(topic, count):
    from engine.budget import requested_items
    assert requested_items(topic) == count
