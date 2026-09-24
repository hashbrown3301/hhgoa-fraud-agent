"""Counts tool calls, tokens and latency per case (required in every answer file)."""
import time
import json
from pathlib import Path


class Tracer:
    def __init__(self, case_id, log_dir="logs"):
        self.case_id = case_id
        self.tool_calls = 0
        self.tokens = 0
        self.events = []
        self._t0 = time.perf_counter()
        self.log_dir = Path(log_dir)

    def tool(self, name, **args):
        """Call once per graph or retrieval call."""
        self.tool_calls += 1
        self.events.append({"t": round(time.perf_counter() - self._t0, 3),
                            "type": "tool", "name": name, "args": args})

    def llm(self, name, tokens):
        """Call once per LLM call with total tokens (prompt + completion)."""
        self.tokens += int(tokens)
        self.events.append({"t": round(time.perf_counter() - self._t0, 3),
                            "type": "llm", "name": name, "tokens": int(tokens)})

    def note(self, text):
        self.events.append({"t": round(time.perf_counter() - self._t0, 3),
                            "type": "note", "text": text})

    @property
    def latency_s(self):
        return round(time.perf_counter() - self._t0, 2)

    def stats(self):
        return {"tool_calls": self.tool_calls, "tokens": self.tokens, "latency_s": self.latency_s}

    def save(self):
        self.log_dir.mkdir(parents=True, exist_ok=True)
        path = self.log_dir / f"{self.case_id}.trace.json"
        path.write_text(json.dumps({"case_id": self.case_id, **self.stats(),
                                    "events": self.events}, indent=2), encoding="utf-8")
        return path