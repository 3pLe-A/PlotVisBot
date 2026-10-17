"""Natural language -> PlotBot math dialect, via the Claude API.

Claude only writes text in the bot's math dialect. That text then goes through
the same whitelist parser as typed math, so model output is never executed.
"""

from __future__ import annotations

import anthropic
from pydantic import BaseModel

SYSTEM = """You translate a user's request (English or Russian) into one formula that a plotting bot can draw.

Write the formula in this plain dialect:
- operators + - * / ^, implicit multiplication allowed ("2 x", "A exp(-k t)")
- functions: sin cos tan asin acos atan sinh cosh tanh exp log sqrt abs sign heaviside erf besselj
- constants: pi, e. Greek letters are spelled out: lambda_1, omega, theta, phi
- coordinates: x y z (Cartesian), t (time), r theta (polar/cylindrical), r theta phi (spherical; theta polar 0..pi, phi azimuth)
- every other single letter or Greek name is a parameter the user can change with buttons
- clauses are separated by ", ": parameter values "A=2", ranges "x in [-5, 5]"

Shapes the bot understands:
- y = f(x)                                   2D curve
- x(t) = f(t)                                quantity over time
- F(x, y) = G(x, y)                          implicit curve
- r = f(theta)                               polar curve
- z = f(x, y)   or   z = f(r, theta)         surface (Cartesian or cylindrical)
- r = f(theta, phi)                          spherical surface
- F(x, y, z) = G(x, y, z)                    implicit surface
- (f(t), g(t)) or (f(t), g(t), h(t))         parametric curve
- (f(u,v), g(u,v), h(u,v))                   parametric surface
- u(x, t) = f(x, t)                          1D field evolving in time (animated)
- u(x, y, t) = f(x, y, t)                    2D field evolving in time (animated)

Rules:
- Solve differential equations analytically when you can, and plot the solution; keep integration
  constants and physical constants as named parameters with sensible values.
- Prefer named parameters over numbers when the user mentions a quantity (amplitude, frequency, decay).
- Choose ranges that show the interesting behaviour.
- explanation: one short sentence in the user's language describing what is plotted.
- If the request cannot be plotted, set ok to false and explain why in the user's language."""

EXAMPLES = [
    ("damped oscillator with frequency 3",
     '{"ok": true, "math": "x(t) = A exp(-gamma t) cos(omega t), A=1, gamma=0.3, omega=3, t in [0, 20]", '
     '"explanation": "Damped harmonic oscillation x(t)."}'),
    ("сфера радиуса 5",
     '{"ok": true, "math": "x^2 + y^2 + z^2 = R^2, R=5", "explanation": "Сфера радиуса R с центром в начале координат."}'),
]


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
