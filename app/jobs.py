"""Background script jobs with a replayable event log.

A job runs write_script() on a thread and records every progress event. Any
number of listeners can attach at any time and receive the full history, then
live events until the job finishes. This is what lets the page start writing
the recommended direction before the user has picked it.
"""

import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable, Iterator

MAX_JOBS = 100


class Job:
    def __init__(self):
        self.id = uuid.uuid4().hex
        self.events: list[dict] = []
        self.done = False
        self._cond = threading.Condition()

    def emit(self, event: dict) -> None:
        with self._cond:
            self.events.append(event)
            self._cond.notify_all()

    def finish(self, event: dict) -> None:
        with self._cond:
            self.events.append(event)
            self.done = True
            self._cond.notify_all()

    def listen(self, heartbeat: float = 15.0) -> Iterator[dict | None]:
        """Yield every event from the start; None means 'still working' (keep-alive)."""
        seen = 0
        while True:
            with self._cond:
                if seen == len(self.events) and not self.done:
                    self._cond.wait(timeout=heartbeat)
                new, finished = self.events[seen:], self.done
            seen += len(new)
            yield from new
            if finished and not new:
                return
            if not new:
                yield None


class JobStore:
    def __init__(self):
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._lock = threading.Lock()

    def start(self, work: Callable[[Callable[[dict], None]], dict]) -> Job:
        """Run work(emit) on a thread; its return value becomes the final 'done' event."""
        job = Job()
        with self._lock:
            self._jobs[job.id] = job
            while len(self._jobs) > MAX_JOBS:
                self._jobs.popitem(last=False)

        def run():
            try:
                job.finish({"type": "done", "result": work(job.emit)})
            except Exception as err:  # surfaced to the page, not swallowed
                job.finish({"type": "error", "message": str(err)})

        threading.Thread(target=run, daemon=True).start()
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)
