"""HTTP layer tests with the LLM swapped for a fake."""

import json

import pytest
from fastapi.testclient import TestClient

import app.main as web
from engine.schemas import DirectionSet, ResearchPlan
from tests.test_pipeline import DIRECTION, GOOD, STRONG, FakeLLM, as_script

BRIEF = {"niche": "Travel", "topic": "best beaches in Dubai", "target_seconds": 30, "tone": "energetic"}


@pytest.fixture
def client(monkeypatch):
    fake = FakeLLM(
        ResearchPlan=[ResearchPlan(needs_research=False, queries=[])],
        DirectionSet=[DirectionSet(directions=[DIRECTION] * 3, recommended_index=2, recommendation_reason="x")],
        ScriptDraft=[GOOD],
        Review=[STRONG],
    )
    monkeypatch.setattr(web, "llm", lambda: fake)
    return TestClient(web.app)


def test_index_and_options(client):
    assert client.get("/").status_code == 200
    opts = client.get("/api/options").json()
    assert opts["lengths"] == [{"value": 30, "words": 75}, {"value": 45, "words": 112}, {"value": 60, "words": 150}]
    assert "energetic" in [t["value"] for t in opts["tones"]]
    assert opts["niches"] == ["Food & restaurants", "Travel", "Personal finance", "Fitness", "Tech"]


def test_directions(client):
    data = client.post("/api/directions", json=BRIEF).json()
    assert len(data["directions"]) == 3
    assert data["recommended_index"] == 2
    assert data["budget"]["total"] == 75
    assert data["budget"]["words_per_second"] == 2.5
    assert data["facts"] == []


def read_events(client, job_id):
    with client.stream("GET", f"/api/jobs/{job_id}/events") as res:
        return [json.loads(line[6:]) for line in res.iter_lines() if line.startswith("data: ")]


def test_script_job_streams_progress_then_result(client):
    job_id = client.post("/api/jobs", json={**BRIEF, "direction": DIRECTION.model_dump()}).json()["job_id"]
    events = read_events(client, job_id)
    assert [e["type"] for e in events] == ["draft_started", "draft_written", "draft_checked", "done"]
    result = events[-1]["result"]
    assert result["script"] == as_script(GOOD).model_dump()
    assert result["review"]["hook_score"] == 5
    assert result["drafts"] == 1


def test_late_listener_replays_full_history(client):
    job_id = client.post("/api/jobs", json={**BRIEF, "direction": DIRECTION.model_dump()}).json()["job_id"]
    first = read_events(client, job_id)
    assert read_events(client, job_id) == first


def test_unknown_job_is_404(client):
    assert client.get("/api/jobs/nope/events").status_code == 404


def test_check_is_deterministic_and_flags_edits(client):
    edited = {**as_script(GOOD).model_dump(), "hook": "Hey guys, welcome back to the channel."}
    data = client.post("/api/check", json={**BRIEF, "script": edited}).json()
    assert "hook_weak_opener" in {i["code"] for i in data["issues"]}


def test_bad_runtime_is_422(client):
    assert client.post("/api/directions", json={**BRIEF, "target_seconds": 5}).status_code == 422


def test_samples_endpoint_serves_saved_runs(client, tmp_path, monkeypatch):
    (tmp_path / "01-best-pizza.json").write_text(json.dumps({"input": {"topic": "best pizza in LA"}}))
    monkeypatch.setattr(web, "SAMPLES", tmp_path)
    data = client.get("/api/samples").json()
    assert data == [{"id": "01-best-pizza", "input": {"topic": "best pizza in LA"}}]
