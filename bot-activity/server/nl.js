// Natural language -> PlotBot math dialect, via the Claude API.
// Claude only writes text in the math dialect; the client parses it with the same
// whitelist parser as typed math, so model output is never executed.

import Anthropic from "@anthropic-ai/sdk";
import { betaZodOutputFormat } from "@anthropic-ai/sdk/helpers/beta/zod";
import { z } from "zod";

const SYSTEM = `You translate a user's request (English or Russian) into one formula that a plotting app can draw.

Write the formula in this plain dialect:
- operators + - * / ^, implicit multiplication allowed ("2 x", "A exp(-k t)")
- functions: sin cos tan asin acos atan sinh cosh tanh exp log sqrt abs sign heaviside erf
- constants: pi, e. Greek letters are spelled out: lambda_1, omega, theta, phi
- coordinates: x y z (Cartesian), t (time), r theta (polar/cylindrical), r theta phi (spherical; theta polar 0..pi, phi azimuth)
- every other single letter or Greek name is a parameter the user can change with a slider
- clauses are separated by ", ": parameter values "A=2", ranges "x in [-5, 5]"

Shapes the app understands:
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
- If the request cannot be plotted, set ok to false and explain why in the user's language.`;

const EXAMPLES = [
  ["damped oscillator with frequency 3",
    '{"ok": true, "math": "x(t) = A exp(-gamma t) cos(omega t), A=1, gamma=0.3, omega=3, t in [0, 20]", "explanation": "Damped harmonic oscillation x(t)."}'],
  ["сфера радиуса 5",
    '{"ok": true, "math": "x^2 + y^2 + z^2 = R^2, R=5", "explanation": "Сфера радиуса R с центром в начале координат."}'],
];

const Translation = z.object({ ok: z.boolean(), math: z.string(), explanation: z.string() });

export class Translator {
  constructor(apiKey, model) {
    this.enabled = Boolean(apiKey);
    this.model = model;
    this.client = apiKey ? new Anthropic({ apiKey }) : null;
  }

  async translate(prompt) {
    if (!this.client) throw new Error("natural-language translation is disabled");
    const messages = EXAMPLES.flatMap(([q, a]) => [{ role: "user", content: q }, { role: "assistant", content: a }]);
    messages.push({ role: "user", content: String(prompt).slice(0, 2000) });
    const response = await this.client.beta.messages.parse({
      model: this.model,
      max_tokens: 2000,
      system: SYSTEM,
      messages,
      output_config: { effort: "low", format: betaZodOutputFormat(Translation) },
      betas: ["server-side-fallback-2026-07-01"],
      fallbacks: "default",
    });
    if (response.stop_reason === "refusal" || !response.parsed_output) throw new Error("the request was declined");
    return response.parsed_output;
  }
}
