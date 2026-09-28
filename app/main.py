"""Web app: a thin HTTP layer over the engine.

    uvicorn app.main:app --reload
"""

import json
import os
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from engine.budget import HOOK_MAX_WORDS, WORDS_PER_SECOND, make_budget, requested_items
from engine.checks import check_script, script_stats
from engine.llm import OpenAILLM, LLMError
from engine.niches import NICHES, get_playbook
from engine.pipeline import MAX_REVISIONS, propose_directions, research, write_script
from engine.prompts import TONES
from engine.schemas import Brief, Direction, Fact, Script

from .jobs import JobStore

load_dotenv()

STATIC = Path(__file__).parent / "static"
SAMPLES = Path(__file__).parent.parent / "samples"

LENGTHS = [30, 45, 60]

app = FastAPI(title="Script Bench")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
jobs = JobStore()


@app.middleware("http")
async def revalidate_assets(request, call_next):
    """Make browsers re-check the page and its assets so updates are never stale."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


def max_revisions() -> int:
    """Rewrite ceiling for the web app. Set MAX_REVISIONS=1 in .env to keep testing cheap;
    make_samples.py always uses the full loop."""
    try:
        return max(0, int(os.getenv("MAX_REVISIONS", MAX_REVISIONS)))
    except ValueError:
        return MAX_REVISIONS


@lru_cache
def llm() -> OpenAILLM:
    return OpenAILLM()


class BriefIn(BaseModel):
    niche: str = Field(min_length=1, max_length=80)
    topic: str = Field(min_length=3, max_length=300)
    target_seconds: int
    tone: str = Field(default="conversational", max_length=80)

    def to_brief(self) -> Brief:
        return Brief(self.niche.strip(), self.topic.strip(), self.target_seconds, self.tone.strip())


class ScriptRequest(BriefIn):
    direction: Direction
    facts: list[Fact] = []


class CheckRequest(BriefIn):
    script: Script


def _budget(seconds: int):
    try:
        return make_budget(seconds)
    except ValueError as err:
        raise HTTPException(422, str(err))


def _issues(issues) -> list[dict]:
    return [{"code": i.code, "message": i.message} for i in issues]


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/options")
def options():
    return {
        "lengths": [{"value": s, "words": make_budget(s).total} for s in LENGTHS],
        "niches": list(NICHES),
        "tones": [{"value": name, "description": desc} for name, desc in TONES.items()],
    }


@app.post("/api/directions")
def directions(req: BriefIn):
    budget = _budget(req.target_seconds)
    try:
        facts = research(req.to_brief(), llm())
        result = propose_directions(req.to_brief(), llm(), budget, facts)
    except LLMError as err:
        raise HTTPException(502, str(err))
    budget_out = asdict(budget) | {
        "total_min": budget.total_min,
        "total_max": budget.total_max,
        "hook_max": HOOK_MAX_WORDS,
        "words_per_second": WORDS_PER_SECOND,
    }
    return {"budget": budget_out, "facts": [f.model_dump() for f in facts], **result.model_dump()}


@app.post("/api/jobs")
def start_script_job(req: ScriptRequest):
    """Start writing a script in the background. Progress streams from /api/jobs/{id}/events."""
    brief, budget, direction, facts = req.to_brief(), _budget(req.target_seconds), req.direction, req.facts
    client = llm()

    def work(emit):
        result = write_script(brief, direction, client, budget, on_progress=emit, facts=facts, max_revisions=max_revisions())
        return {
            "script": result.script.model_dump(),
            "stats": script_stats(result.script),
            "issues": _issues(result.issues),
            "review": result.review.model_dump() if result.review else None,
            "drafts": len(result.drafts),
        }

    return {"job_id": jobs.start(work).id}


@app.get("/api/jobs/{job_id}/events")
def job_events(job_id: str):
    """Server-sent events: the job's full history, then live updates until done."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job")

    def stream():
        for event in job.listen():
            yield ": keep-alive\n\n" if event is None else f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/samples")
def samples():
    """The saved sample runs from make_samples.py, exactly as generated."""
    return [
        {"id": path.stem, **json.loads(path.read_text())}
        for path in sorted(SAMPLES.glob("*.json"))
    ]


@app.post("/api/check")
def check(req: CheckRequest):
    """Deterministic re-check for live editing. No LLM call, so it's instant and free."""
    budget = _budget(req.target_seconds)
    playbook = get_playbook(req.niche)
    banned = playbook.banned_phrases if playbook else ()
    return {"stats": script_stats(req.script), "issues": _issues(check_script(req.script, budget, banned, requested_items(req.topic)))}
