"""Natural language -> PlotBot math dialect, via the Claude API.

Claude only writes text in the bot's math dialect. That text then goes through
the same whitelist parser as typed math, so model output is never executed.
"""

from __future__ import annotations

import json
from pathlib import Path

import anthropic
from pydantic import BaseModel

# Prompt and examples are shared with activity-type (../shared/nl).
SHARED = Path(__file__).resolve().parents[2] / "shared" / "nl"
SYSTEM = (SHARED / "system.txt").read_text(encoding="utf-8")
EXAMPLES = [(e["prompt"], json.dumps(e["answer"], ensure_ascii=False))
            for e in json.loads((SHARED / "examples.json").read_text(encoding="utf-8"))]


class Translation(BaseModel):
    ok: bool
    math: str
    explanation: str


class Translator:
    def __init__(self, api_key: str | None, model: str) -> None:
        self.enabled = bool(api_key)
        self.model = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key) if api_key else None

    async def translate(self, prompt: str) -> Translation:
        if not self._client:
            raise RuntimeError("natural-language translation is disabled")
        messages = []
        for q, a in EXAMPLES:
            messages += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
        messages.append({"role": "user", "content": prompt[:2000]})
        response = await self._client.beta.messages.parse(
            model=self.model,
            max_tokens=2000,
            system=SYSTEM,
            messages=messages,
            output_format=Translation,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise RuntimeError("the request was declined")
        return response.parsed_output
