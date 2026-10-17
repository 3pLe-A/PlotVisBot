// Registers the /plot slash command. When the command is used, the server answers with
// LAUNCH_ACTIVITY, so the Activity opens with the prompt already filled in.
// Commands are created one by one (not bulk-overwritten) so Discord's Activity
// entry-point command is left untouched.

import "dotenv/config";

const appId = process.env.VITE_DISCORD_CLIENT_ID;
const token = process.env.DISCORD_TOKEN;
if (!appId || !token) {
  console.error("Set VITE_DISCORD_CLIENT_ID and DISCORD_TOKEN in .env first.");
  process.exit(1);
}

const command = {
  name: "plot",
  type: 1,
  description: "Open the live plot with a formula or description",
  description_localizations: { ru: "Открыть живой график по формуле или описанию" },
  options: [{
    type: 3,
    name: "prompt",
    description: "Math (LaTeX or plain) or a description",
    description_localizations: { ru: "Формула (LaTeX или обычная) или описание" },
    required: true,
    max_length: 1500,
  }],
  integration_types: [0],
  contexts: [0, 1, 2],
};

const res = await fetch(`https://discord.com/api/v10/applications/${appId}/commands`, {
  method: "POST",
  headers: { Authorization: `Bot ${token}`, "Content-Type": "application/json" },
  body: JSON.stringify(command),
});
console.log(res.ok ? "Registered /plot" : `Failed: ${res.status} ${await res.text()}`);
