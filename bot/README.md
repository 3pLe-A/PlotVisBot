# PlotBot for Discord: buttons and form version

A Discord bot that turns a prompt into a plot. Typed math (LaTeX, plain or Mathematica-style) is parsed directly. A natural-language prompt (English or Russian) is first rewritten as math by Claude, then plotted. Every plot has controls for its parameters: buttons step a value up or down, and a pop-up form sets exact values and the axis range. Each change redraws the image in the same message.

The other bot in this repository, [`activity-type`](../activity-type), is the Discord Activity version, with live sliders and 3D rotation.

## What it draws

| Input | Plot |
|---|---|
| `y = sin(k x)`, `sin(x)` | 2D curve |
| `x(t) = A e^{-\lambda_1 t} + B e^{-\lambda_2 t}` | quantity over time |
| `y^2 = x^3 - x`, `\frac{x^2}{a^2} + \frac{y^2}{b^2} = 1` | implicit curve |
| `r = 1 + cos(theta)` | polar curve |
| `x = cos(3t), y = sin(2t)` or `(cos t, sin t, t/5)` | parametric curve (2D or 3D) |
| `z = x^2 - y^2` | surface |
| `z = r^2 sin(theta)` | surface in cylindrical coordinates |
| `r = 1 + 0.3 sin(3 theta) sin(4 phi)` | surface in spherical coordinates (θ polar, φ azimuth) |
| `x^2 + y^2 + z^2 = 25` | implicit surface |
| `((2 + cos v) cos u, (2 + cos v) sin u, sin v)` | parametric surface |
| `u(x,t) = sin(x - c t)` | 1D + time: animated GIF plus a spacetime (x, t) diagram |
| `u = exp(-(x^2+y^2)/(1+t)) cos(omega t)` | 2D + time: animated heatmap |

The coordinates are `x y z t r theta phi` (and `u v s` in parametric forms). Every other letter or Greek name is a parameter with its own buttons, starting at 1. You can add clauses after a comma:

- a parameter value: `A=2`, `\lambda_1 = 0.5`
- a range: `x in [0, 10]`, `t = 0..5` or `0 < x < pi`

Unicode (`λ`, `²`, `π`), LaTeX (`\frac`, `\sqrt`, `\left(`, `_{1}`) and Mathematica brackets (`Exp[-t]`, `x[t]`) are all accepted.

## Commands

- `/plot prompt` draws the plot. The reply shows the formula as LaTeX, the parameter values and ranges, the image, and the controls.
- `/tex source` renders LaTeX text and math, including Cyrillic text, for example `Решение: $x(t) = A e^{-\lambda t}$`. A formula with no `$` is rendered as math.
- `/language` switches the bot's replies between English and Russian. Without it, the language follows the prompt (Cyrillic means Russian) or the user's Discord locale.
- `/help` lists examples.

## Setting it up

### 1. Create the Discord application

1. Open the [Discord Developer Portal](https://discord.com/developers/applications) and choose **New Application**.
2. Open **Bot**, choose **Reset Token**, and copy the token into `.env` as `DISCORD_TOKEN`. No privileged intents are needed, because the bot only uses slash commands.
3. Open **Installation** (or **OAuth2 → URL Generator**). Select the scopes `bot` and `applications.commands`, and the permissions View Channels, Send Messages, Embed Links and Attach Files.

### 2. Run it

Python 3.11 or later is required.

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                    # then fill in DISCORD_TOKEN (and ANTHROPIC_API_KEY)
python -m plotbot
```

On start-up the bot logs an **invite link**:

```
https://discord.com/oauth2/authorize?client_id=<APP_ID>&scope=bot+applications.commands&permissions=51200
```

Send that link to any server admin. Opening it adds the bot to their server.

Slash commands sync globally on start-up, and Discord can take up to an hour to show them everywhere. While testing, set `DEV_GUILD_ID` to your server's ID so they appear immediately.

### 3. Natural-language prompts (optional)

Set `ANTHROPIC_API_KEY` to enable prompts such as *"a damped oscillator with frequency 3"* or *"сфера радиуса 5"*. Claude writes the formula in the bot's math dialect, and that text goes through the same whitelist parser as typed math, so model output is never executed. Without a key, typed math still works. The model is set by `PLOTBOT_MODEL`.

## Storage

The bot uses one SQLite file (`PLOTBOT_DB`). It keeps one row per plot with:

- the prompt
- the formula
- the current and initial parameter values
- the ranges
- the server, channel, message and user IDs

That is about 1 KB per plot. Images are not stored: each one is redrawn from the row whenever someone presses a button. Rows untouched for `PLOTBOT_RETENTION_DAYS` days (30 by default) are deleted hourly, and their buttons then reply that the plot has expired. A public bot that stores user content needs a privacy policy under Discord's developer terms.

## Security notes

- Prompts never reach `eval` unchecked. Every identifier must be a whitelisted function, constant or symbol name, attribute access and dunder names are refused, and SymPy's parser runs with empty `__builtins__` (see `tests/test_parse.py`).
- Rendering runs in separate processes with a time limit (`PLOTBOT_RENDER_TIMEOUT`).
- `/tex` uses Matplotlib mathtext by default, so no TeX installation runs. If you set `PLOTBOT_USETEX=1`, real LaTeX runs, and commands that read or write files or redefine TeX are refused.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## Layout

```
plotbot/
  bot.py        slash commands, buttons, the form, redraws
  mathparse.py  safe parser: plain / LaTeX / Mathematica -> PlotSpec, plot-type detection
  render.py     Matplotlib renderer (PNG, animated GIF), dark theme
  nl.py         natural language -> math via Claude (prompt in ../shared/nl)
  texcard.py    /tex renderer (mathtext or real LaTeX)
  storage.py    SQLite store and retention
  i18n.py       English and Russian strings
  spec.py       PlotSpec, serialised as JSON
```
