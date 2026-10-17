# PlotBot Activity: live sliders version

A Discord Activity (a web app that runs inside Discord) that turns a prompt into a live plot. Each parameter gets a slider that redraws the plot as you drag. 3D plots rotate and zoom with the mouse or touch, and time-dependent plots play, pause and scrub.

The other bot in this repository, [`bot-buttons`](../bot-buttons), is the classic version, where buttons and a form redraw an image.

The same app also runs **standalone on localhost**, so you can test everything except Discord sign-in in an ordinary browser.

## What it draws

Prompts are written the same way as in the bot version: LaTeX, plain math or Mathematica-style, plus natural language (English or Russian) when an Anthropic API key is set.

| Input | Plot |
|---|---|
| `x(t) = A e^{-\lambda_1 t} + B e^{-\lambda_2 t}` | curve over time, with sliders for A, B, λ₁, λ₂ |
| `x^2 + y^2 + z^2 = R^2, R=5` | implicit surface (isosurface) |
| `y^2 = x^3 - x` | implicit curve |
| `r = 1 + cos(theta)` | polar curve |
| `z = sin(a x) cos(b y)` | surface |
| `z = r^2 sin(theta)` | surface in cylindrical coordinates |
| `r = 1 + a sin(3 theta) sin(4 phi)` | surface in spherical coordinates (θ polar, φ azimuth) |
| `(cos t, sin t, t/5)`, `x = cos(3t), y = sin(2t)` | parametric curves |
| `((R + cos v) cos u, (R + cos v) sin u, sin v)` | parametric surface |
| `u(x,t) = A sin(k x - omega t)` | 1D + time: animated profile plus a spacetime (x, t) diagram |
| `u = exp(-(x^2+y^2)/(1+D t)) cos(omega t)` | 2D + time: animated heatmap |

You can add `, A=2` to set a starting value and `, x in [0, 10]` to set a range. Ranges can also be edited in the side panel, and each slider's min and max can be changed there too.

**Save** stores the plot and gives it an ID such as `#5e5d703f894d`. Typing that ID in the prompt box reopens it. In standalone mode, `?plot=<id>` in the URL also works.

## Run it on localhost

Node 22.13 or later is required.

```bash
npm install
cp .env.example .env        # optional for localhost: add ANTHROPIC_API_KEY for natural-language prompts
npm run dev                 # API server on :3001 + Vite dev server on :5173
```

Open <http://localhost:5173>. Typed math works with no keys at all.

Other scripts:

- `npm test` runs the parser and server tests.
- `npm run build && npm start` builds the client and serves everything from one Node process on `PORT` (3001 by default).

## Run it inside Discord

1. **Create an application** in the [Developer Portal](https://discord.com/developers/applications). It can be the bot version's application or a separate one.
2. **OAuth2**: copy the Client ID into `VITE_DISCORD_CLIENT_ID` and the Client Secret into `DISCORD_CLIENT_SECRET`. Add `https://127.0.0.1` as a redirect URI; the Embedded App SDK needs one to exist, even though it is never visited.
3. **Expose your local server over https.** Discord only loads Activities from public https URLs. For example:
   ```bash
   cloudflared tunnel --url http://localhost:5173
   TUNNEL=1 npm run dev
   ```
4. **Activities → URL Mappings**: map `/` to the tunnel host, without `https://` (for example `something.trycloudflare.com`). Then go to **Activities → Settings** and enable Activities.
5. In Discord, open the **App Launcher** (the rocket icon in a voice channel or text channel) and start your app. While the app is unpublished, only you and the testers you add under **App Testers** can see it.

### The `/plot` slash command (optional)

`/plot prompt:<formula>` opens the Activity with the prompt already plotted:

1. Copy the bot token into `DISCORD_TOKEN` and the Public Key into `DISCORD_PUBLIC_KEY`.
2. Set **General Information → Interactions Endpoint URL** to `https://<tunnel-host>/interactions`.
3. Run `npm run register` once.

The server stores the prompt for that user and replies with Discord's *launch Activity* response. The Activity then picks the prompt up after sign-in.

### Moving to a real host

Run `npm run build && npm start` on the host, which needs Node 22.13 or later and a persistent disk for the SQLite file. Point the URL mapping and the Interactions Endpoint at that host's https address instead of the tunnel.

## Storage

The app uses one SQLite file (`PLOTBOT_DB`). Saved plots keep only text:

- the prompt
- the formula
- the parameter values
- the ranges
- the user and channel IDs

That is about 1 KB each. Rows are deleted after `PLOTBOT_RETENTION_DAYS` days (30 by default). Unsaved plots are never stored. Prompts sent with `/plot` are kept in memory for at most 10 minutes, until the Activity picks them up.

## Limitations

- Each participant's sliders are their own. Several people in the same Activity don't yet see each other's changes; that would need a WebSocket sync layer.
- Implicit 3D surfaces are sampled on a 34³ grid to keep sliders smooth, so very thin features can look coarse. Narrowing the ranges increases the detail.
- Natural-language prompts call the Claude API (`PLOTBOT_MODEL`, default `claude-opus-5-5`). Claude only writes math text, which the browser then parses with the same whitelist parser as typed input.

## Security notes

- Expressions are parsed and evaluated by math.js. Only whitelisted names are accepted, and the math.js functions an expression could use to reach the parser (`import`, `evaluate`, `parse` and others) are disabled.
- The Discord client secret and the Anthropic key stay on the server. Only `VITE_DISCORD_CLIENT_ID`, which is public, is bundled into the page.
- `/interactions` verifies Discord's request signature with `DISCORD_PUBLIC_KEY`.

## Layout

```
client/
  index.html, src/main.js   UI: prompt, sliders, time controls, ranges, save/load, EN/RU
  src/mathparse.js          safe parser and plot-type detection (math.js)
  src/figure.js             Plotly figures for each plot type
  src/discord.js            Embedded App SDK sign-in and the /plot hand-off
  src/i18n.js               English and Russian strings, examples
server/
  index.js                  Express: OAuth token, /interactions, translation, saved plots
  nl.js                     natural language -> math via Claude (prompt in ../shared/nl)
  db.js                     SQLite store and retention
scripts/register-commands.js
test/                       node:test suites
```
