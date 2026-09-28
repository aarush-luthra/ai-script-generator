"""The only module that knows which LLM provider we use.

The rest of the engine depends on the `LLM` protocol: give it instructions,
input and a Pydantic schema, get back a validated instance. Swapping providers,
or substituting a fake in tests, touches nothing else.
"""

import os
from typing import Literal, Protocol, TypeVar

from dotenv import load_dotenv
from openai import NOT_GIVEN, OpenAI
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "gpt-6-luna"

# The writer can use its own model (OPENAI_WRITER_MODEL): drafts are where model
# quality shows. Measured on the hardest topic, gpt-5-mini was slower at medium
# effort and never passed the editor at low, so the default writer is the same
# as everything else until a stronger model proves itself.
DEFAULT_WRITER_MODEL = DEFAULT_MODEL
WRITER_STAGES = {"script", "revision"}


class LLMError(RuntimeError):
    pass


Effort = Literal["none", "low", "medium", "high"]


class LLM(Protocol):
    def parse(self, instructions: str, input: str, schema: type[T], effort: Effort | None = None, stage: str | None = None) -> T: ...

    def search(self, instructions: str, input: str, schema: type[T], effort: Effort | None = None) -> tuple[T, set[str]]:
        """Like parse, but the model may search the web. Also returns every URL the search actually visited."""
        ...


class OpenAILLM:
    def __init__(self, model: str | None = None):
        load_dotenv()
        if not os.getenv("OPENAI_API_KEY"):
            raise LLMError("OPENAI_API_KEY is not set. Add it to .env (see .env.example).")
        self.model = model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
        self.writer_model = os.getenv("OPENAI_WRITER_MODEL", DEFAULT_WRITER_MODEL)
        self._client = OpenAI()

    def model_for(self, stage: str | None) -> str:
        return self.writer_model if stage in WRITER_STAGES else self.model

    def parse(self, instructions: str, input: str, schema: type[T], effort: Effort | None = None, stage: str | None = None) -> T:
        response = self._client.responses.parse(
            model=self.model_for(stage),
            instructions=instructions,
            input=input,
            text_format=schema,
            reasoning={"effort": effort} if effort else NOT_GIVEN,
            max_output_tokens=16000,
        )
        return self._parsed(response)

    def search(self, instructions: str, input: str, schema: type[T], effort: Effort | None = None) -> tuple[T, set[str]]:
        response = self._client.responses.parse(
            model=self.model,
            instructions=instructions,
            input=input,
            text_format=schema,
            tools=[{"type": "web_search"}],
            include=["web_search_call.action.sources"],
            reasoning={"effort": effort} if effort else NOT_GIVEN,
            max_output_tokens=16000,
        )
        visited = {
            source.url
            for item in response.output
            if item.type == "web_search_call"
            for source in (getattr(getattr(item, "action", None), "sources", None) or [])
            if getattr(source, "url", None)
        }
        return self._parsed(response), visited

    @staticmethod
    def _parsed(response):
        if response.status == "incomplete":
            raise LLMError(f"Model response was incomplete: {response.incomplete_details}")
        if response.output_parsed is None:
            raise LLMError("Model returned no parseable output (possibly a refusal).")
        return response.output_parsed
