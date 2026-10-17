# PlotBot

Two Discord bots that turn a prompt into an interactive plot. Typed math (LaTeX, plain or Mathematica-style) is plotted directly. A natural-language prompt in English or Russian is first rewritten as math by Claude, then plotted. Both bots take the same input, understand the same 12 plot types and keep only text in their database. They differ in how you change a plot's parameters:

| | [`bot-buttons`](bot-buttons) | [`bot-activity`](bot-activity) |
|---|---|---|
| Runs as | an ordinary Discord bot (Python) | a Discord Activity: a web app inside Discord (Node/npm) |
| Changing parameters | buttons step a value; a pop-up form sets exact values and ranges | live sliders, drag-to-rotate 3D, play/pause for time |
| Output | a PNG, or a GIF for time-dependent plots, edited in place in the chat | an interactive Plotly view |
| Needs | a bot token | an https host (or a tunnel while testing), plus OAuth client ID and secret |
| Try it locally | `python -m plotbot` (connects to Discord) | `npm run dev`, then open http://localhost:5173 (works without Discord) |

## Layout

```
bot-buttons/    Python bot: /plot, /tex, /language, /help; buttons and form; Matplotlib renderer
bot-activity/   Activity: Vite + Plotly client, Express server, optional /plot launcher command
shared/
  nl/                 prompt and examples Claude uses to rewrite natural language as math (both bots)
  parser-cases.json   inputs both parsers must classify identically, plus inputs both must refuse
```

Each bot has its own README with setup steps, its own `.env.example` and its own tests. They share only the `shared/` folder, so either bot can be deployed on its own together with `shared/`.

## Plot types

| Input | Plot |
|---|---|
| `y = sin(k x)` | 2D curve |
| `x(t) = A e^{-\lambda_1 t} + B e^{-\lambda_2 t}` | quantity over time |
| `y^2 = x^3 - x` | implicit curve |
| `r = 1 + cos(theta)` | polar curve |
| `x = cos(3t), y = sin(2t)` or `(cos t, sin t, t/5)` | parametric curve |
| `z = x^2 - y^2` | surface |
| `z = r^2 sin(theta)` | cylindrical surface |
| `r = 1 + 0.3 sin(3 theta) sin(4 phi)` | spherical surface |
| `x^2 + y^2 + z^2 = 25` | implicit surface |
| `(cos(u) sin(v), sin(u) sin(v), cos(v))` | parametric surface |
| `u(x,t) = sin(x - c t)` | 1D + time, with a spacetime diagram |
| `u = exp(-(x^2+y^2)/(1+t)) cos(omega t)` | 2D + time |

Every symbol that isn't a coordinate (`x y z t r theta phi`) becomes an adjustable parameter. You can add `, A=2` to set a starting value and `, x in [0, 10]` to set a range.

## Tests

```bash
cd bot-buttons && pip install -r requirements-dev.txt && python -m pytest
cd bot-activity && npm install && npm test
```

Both suites read `shared/parser-cases.json`, so a change to one parser that the other doesn't match shows up as a failing test.

## Storage

Each bot keeps a small SQLite file holding text only: the prompt, the formula, the parameter values, the ranges and the Discord IDs. That is about 1 KB per plot, kept for 30 days by default. Images already posted in the chat stay; only the plot's controls stop working after the retention period.
