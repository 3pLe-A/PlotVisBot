import asyncio

from plotbot.bot import PlotBot, _step, pretty
from plotbot.config import Config
from plotbot.mathparse import parse_math


def _cfg(tmp_path):
    return Config(discord_token="x", anthropic_api_key=None, model="claude-opus-5-5",
                  db_path=str(tmp_path / "t.sqlite3"), retention_days=30, owner_only=False,
                  dev_guild_id=None, render_workers=1, render_timeout=60, usetex=False)


def test_pretty_and_step():
    assert pretty("lamda_1") == "λ₁" and pretty("omega") == "ω" and pretty("A") == "A"
    assert _step(0) == 0.1 and _step(2) == 0.2 and _step(150) == 20


def test_view_embed_and_render(tmp_path):
    async def main():
        bot = PlotBot(_cfg(tmp_path))
        try:
            spec = parse_math(r"x(t) = A e^{-\lambda_1 t} + B e^{-\lambda_2 t}")
            state = {"selected": "A", "steps": {n: 0.1 for n in spec.params}, "initial": dict(spec.params),
                     "explanation": None}
            view = bot.view("abc123", spec, state, "ru")
            ids = [c.custom_id for c in view.children]
            assert ids[0] == "pb:sel:abc123" and "pb:inc:abc123" in ids and "pb:form:abc123" in ids
            assert all(len(i) <= 100 for i in ids)
            embed = bot.embed(spec, state, "en", "plot.png")
            assert "λ₁ = 1" in embed.description and embed.image.url == "attachment://plot.png"
            spec2, expl = await bot.make_spec("y = sin(k x)")
            assert spec2.kind == "explicit2d" and expl is None
            file = await bot.render(spec)
            assert file.filename == "plot.png"
        finally:
            bot.pool.shutdown()
            await bot.http.close()

    asyncio.run(main())


def test_natural_language_path(tmp_path):
    from plotbot.nl import Translation

    async def main():
        bot = PlotBot(_cfg(tmp_path))

        async def fake(prompt):
            return Translation(ok=True, math="x(t) = A exp(-gamma t) cos(omega t), A=1, gamma=0.3, omega=3",
                               explanation="Затухающие колебания.")

        bot.translator.enabled = True
        bot.translator.translate = fake
        try:
            spec, expl = await bot.make_spec("затухающий осциллятор с частотой 3")
            assert spec.kind == "explicit2d" and spec.params["omega"] == 3 and expl.startswith("Затух")
            assert spec.source == "затухающий осциллятор с частотой 3"
        finally:
            bot.pool.shutdown()
            await bot.http.close()

    asyncio.run(main())
