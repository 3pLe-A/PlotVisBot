// Natural language -> PlotBot math dialect, via the Claude API.
// Claude only writes text in the math dialect; the client parses it with the same
// whitelist parser as typed math, so model output is never executed.

import { readFileSync } from "node:fs";
import Anthropic from "@anthropic-ai/sdk";
import { betaZodOutputFormat } from "@anthropic-ai/sdk/helpers/beta/zod";
import { z } from "zod";

// Prompt and examples are shared with bot-buttons (../shared/nl).
const shared = new URL("../../shared/nl/", import.meta.url);
const SYSTEM = readFileSync(new URL("system.txt", shared), "utf8");
const EXAMPLES = JSON.parse(readFileSync(new URL("examples.json", shared), "utf8"))
  .map((e) => [e.prompt, JSON.stringify(e.answer)]);

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
