// Express server: Discord OAuth token exchange, the /plot slash command (launches the
// Activity), natural-language translation and saved plots. In production it also
// serves the built client from client/dist.

import "dotenv/config";
import express from "express";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { InteractionResponseType, InteractionType, verifyKeyMiddleware } from "discord-interactions";
import { Store } from "./db.js";
import { Translator } from "./nl.js";

const env = process.env;
const PORT = Number(env.PORT || 3001);
const PENDING_TTL_MS = 10 * 60_000;
const root = dirname(dirname(fileURLToPath(import.meta.url)));

const store = new Store(env.PLOTBOT_DB || "plotbot-activity.sqlite3", Number(env.PLOTBOT_RETENTION_DAYS || 30));
const translator = new Translator(env.ANTHROPIC_API_KEY, env.PLOTBOT_MODEL || "claude-opus-5-5");
// Prompts typed into /plot wait here until that user's Activity opens and collects them.
const pending = new Map();

export const app = express();
app.disable("x-powered-by");

// --------------------------------------------------------------------------- Discord interactions
// Must come before express.json(): signature verification needs the raw body.
if (env.DISCORD_PUBLIC_KEY) {
  app.post("/interactions", verifyKeyMiddleware(env.DISCORD_PUBLIC_KEY), (req, res) => {
    const { type, data } = req.body;
    if (type === InteractionType.PING) return res.send({ type: InteractionResponseType.PONG });
    if (type === InteractionType.APPLICATION_COMMAND && data.name === "plot") {
      const user = req.body.member?.user ?? req.body.user;
      const prompt = data.options?.find((o) => o.name === "prompt")?.value ?? "";
      pending.set(user.id, { prompt, channelId: req.body.channel_id, at: Date.now() });
      return res.send({ type: InteractionResponseType.LAUNCH_ACTIVITY });
    }
    return res.status(400).send({ error: "unknown interaction" });
  });
}

app.use(express.json({ limit: "64kb" }));

// --------------------------------------------------------------------------- OAuth for the Embedded App SDK

app.post("/api/token", async (req, res) => {
  const response = await fetch("https://discord.com/api/oauth2/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: env.VITE_DISCORD_CLIENT_ID,
      client_secret: env.DISCORD_CLIENT_SECRET,
      grant_type: "authorization_code",
      code: String(req.body.code || ""),
    }),
  });
  const json = await response.json();
  if (!response.ok) return res.status(400).send({ error: json.error || "token exchange failed" });
  res.send({ access_token: json.access_token });
});

async function discordUser(req) {
  const auth = req.get("authorization");
  if (!auth?.startsWith("Bearer ")) return null;
  const r = await fetch("https://discord.com/api/users/@me", { headers: { Authorization: auth } });
  return r.ok ? r.json() : null;
}

app.get("/api/pending", async (req, res) => {
  const user = await discordUser(req);
  if (!user) return res.status(401).send({ error: "not signed in" });
  const item = pending.get(user.id);
  pending.delete(user.id);
  res.send(item && Date.now() - item.at < PENDING_TTL_MS ? { prompt: item.prompt } : {});
});

// --------------------------------------------------------------------------- translation and saved plots

app.get("/api/config", (_req, res) => res.send({ naturalLanguage: translator.enabled }));

app.post("/api/translate", async (req, res) => {
  if (!translator.enabled) return res.status(503).send({ error: "natural-language prompts are disabled" });
  try {
    res.send(await translator.translate(String(req.body.prompt || "")));
  } catch (e) {
    console.warn("translation failed:", e.message);
    res.status(502).send({ error: e.message });
  }
});

app.post("/api/plots", async (req, res) => {
  const { lang, prompt, state } = req.body || {};
  if (typeof prompt !== "string" || typeof state !== "object" || !state) return res.status(400).send({ error: "bad plot" });
  const user = await discordUser(req);
  const id = store.save({ userId: user?.id, channelId: req.body.channelId, lang: lang === "ru" ? "ru" : "en",
    prompt: prompt.slice(0, 2000), state });
  res.send({ id });
});

app.get("/api/plots/:id", (req, res) => {
  const row = store.get(req.params.id);
  if (!row) return res.status(404).send({ error: "not found" });
  res.send({ id: row.id, lang: row.lang, prompt: row.prompt, state: row.state });
});

// --------------------------------------------------------------------------- static client (production)

const dist = join(root, "client", "dist");
if (env.NODE_ENV === "production" && existsSync(dist)) {
  app.use(express.static(dist));
  app.get("/{*path}", (_req, res) => res.sendFile(join(dist, "index.html")));
}

setInterval(() => store.purgeExpired(), 3_600_000).unref();
setInterval(() => {
  for (const [k, v] of pending) if (Date.now() - v.at > PENDING_TTL_MS) pending.delete(k);
}, 60_000).unref();

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  store.purgeExpired();
  app.listen(PORT, () => {
    console.log(`PlotBot Activity server on http://localhost:${PORT}`);
    if (!translator.enabled) console.log("ANTHROPIC_API_KEY not set: only typed math works.");
    if (!env.DISCORD_PUBLIC_KEY) console.log("DISCORD_PUBLIC_KEY not set: the /plot slash command endpoint is off.");
  });
}
