// Discord Embedded App SDK: only used when the page runs inside Discord as an Activity.
// On plain localhost (no frame_id in the URL) the app runs standalone.

import { DiscordSDK } from "@discord/embedded-app-sdk";

export function insideDiscord() {
  return new URLSearchParams(location.search).has("frame_id");
}

/** Authenticate with Discord and return { sdk, accessToken, user, prompt } (prompt from /plot, if any). */
export async function connectDiscord() {
  const clientId = import.meta.env.VITE_DISCORD_CLIENT_ID;
  const sdk = new DiscordSDK(clientId);
  await sdk.ready();
  const { code } = await sdk.commands.authorize({
    client_id: clientId,
    response_type: "code",
    state: "",
    prompt: "none",
    scope: ["identify"],
  });
  const tokenRes = await fetch("/api/token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });
  const { access_token: accessToken } = await tokenRes.json();
  const auth = await sdk.commands.authenticate({ access_token: accessToken });
  const pending = await fetch("/api/pending", { headers: { Authorization: `Bearer ${accessToken}` } })
    .then((r) => (r.ok ? r.json() : {}))
    .catch(() => ({}));
  return { sdk, accessToken, user: auth.user, prompt: pending.prompt, channelId: sdk.channelId };
}
