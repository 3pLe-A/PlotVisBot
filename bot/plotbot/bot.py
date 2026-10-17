"""Discord front end: slash commands, buttons, the parameter form and redraws."""

from __future__ import annotations

import asyncio
import io
import logging
import math
import multiprocessing
import secrets
import time
from concurrent.futures import ProcessPoolExecutor

import discord
from discord import app_commands
from discord.ext import tasks

from . import i18n
from .config import Config
from .i18n import t
from .mathparse import GREEK_UNICODE, MathParseError, looks_like_math, number, parse_math
from .nl import Translator
from .render import RenderError, render_json
from .spec import PlotSpec
from .storage import PlotRow, Store
from .texcard import TexError, render_tex

log = logging.getLogger("plotbot")

EMBED_COLOR = 0x3987E5
MAX_ABS = 1e6
INVITE_PERMISSIONS = 51200  # View Channel, Send Messages, Embed Links, Attach Files
_GREEK_BY_NAME = {v: k for k, v in GREEK_UNICODE.items()}
_SUBSCRIPT = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def pretty(name: str) -> str:
    """lamda_1 -> λ₁, omega -> ω, A -> A."""
    base, _, sub = name.partition("_")
    base = _GREEK_BY_NAME.get(base, base)
    if sub:
        sub = sub.translate(_SUBSCRIPT) if sub.isdigit() else f"_{sub}"
    return base + sub


def _step(value: float) -> float:
    raw = 0.1 * max(abs(value), 1.0)
    return float(f"{raw:.1g}")


class PlotBot(discord.Client):
    def __init__(self, cfg: Config) -> None:
        super().__init__(intents=discord.Intents.default())
        self.cfg = cfg
        self.tree = app_commands.CommandTree(self)
        self.store = Store(cfg.db_path, cfg.retention_days)
        self.translator = Translator(cfg.anthropic_api_key, cfg.model)
        self.pool = ProcessPoolExecutor(cfg.render_workers, mp_context=multiprocessing.get_context("spawn"))
        self.locks: dict[str, asyncio.Lock] = {}
        _register_commands(self)

    async def setup_hook(self) -> None:
        if self.cfg.dev_guild_id:
            guild = discord.Object(id=self.cfg.dev_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
        self.purge.start()

    async def on_ready(self) -> None:
        log.info("Logged in as %s", self.user)
        log.info(
            "Invite link: https://discord.com/oauth2/authorize?client_id=%s&scope=bot+applications.commands&permissions=%d",
            self.user.id, INVITE_PERMISSIONS,
        )

    async def close(self) -> None:
        self.pool.shutdown(cancel_futures=True)
        await super().close()

    @tasks.loop(hours=1)
    async def purge(self) -> None:
        removed = self.store.purge_expired()
        if removed:
            log.info("Purged %d expired plots", removed)

    # ------------------------------------------------------------------ pipeline

    def lang_for(self, interaction: discord.Interaction, text: str = "") -> str:
        return self.store.get_lang(interaction.user.id) or i18n.detect(text, str(interaction.locale))

    async def make_spec(self, prompt: str) -> tuple[PlotSpec, str | None]:
        """Math goes straight to the parser; anything else goes through Claude first."""
        if looks_like_math(prompt) or not self.translator.enabled:
            try:
                return parse_math(prompt), None
            except MathParseError:
                if not self.translator.enabled:
                    raise
        result = await self.translator.translate(prompt)
        if not result.ok:
            raise RuntimeError(result.explanation)
        spec = parse_math(result.math)
        spec.source = prompt
        return spec, result.explanation

    async def render(self, spec: PlotSpec) -> discord.File:
        loop = asyncio.get_running_loop()
        data, name = await asyncio.wait_for(
            loop.run_in_executor(self.pool, render_json, spec.to_json()), self.cfg.render_timeout
        )
        return discord.File(io.BytesIO(data), filename=name)

    def embed(self, spec: PlotSpec, state: dict, lang: str, filename: str) -> discord.Embed:
        lines = []
        if state.get("explanation"):
            lines.append(f"**{t(lang, 'rewritten')}:** {state['explanation']}")
        lines.append(f"```latex\n{spec.latex}\n```")
        if spec.params:
            values = ", ".join(f"{pretty(k)} = {v:g}" for k, v in sorted(spec.params.items()))
            lines.append(f"**{t(lang, 'parameters')}:** {values}")
        ranges = "   ".join(f"{pretty(k)} ∈ [{a:g}, {b:g}]" for k, (a, b) in spec.ranges.items())
        lines.append(ranges)
        if spec.time:
            lines.append(t(lang, "animated", time=pretty(spec.time)))
        e = discord.Embed(color=EMBED_COLOR, description="\n".join(lines)[:4000])
        e.set_image(url=f"attachment://{filename}")
        e.set_footer(text=spec.source[:200])
        return e

    def view(self, plot_id: str, spec: PlotSpec, state: dict, lang: str) -> discord.ui.View:
        view = discord.ui.View(timeout=None)
        names = sorted(spec.params)
        selected = state.get("selected")
        if names:
            if len(names) > 1:
                view.add_item(discord.ui.Select(
                    custom_id=f"pb:sel:{plot_id}",
                    placeholder=t(lang, "pick_param"),
                    options=[discord.SelectOption(label=f"{pretty(n)} = {spec.params[n]:g}", value=n,
                                                  default=n == selected) for n in names[:25]],
                    row=0,
                ))
            for action, symbol in (("dec2", "−−"), ("dec", "−"), ("inc", "+"), ("inc2", "++")):
                view.add_item(discord.ui.Button(label=f"{pretty(selected)} {symbol}", custom_id=f"pb:{action}:{plot_id}",
                                                style=discord.ButtonStyle.secondary, row=1))
        view.add_item(discord.ui.Button(label=t(lang, "set_values"), custom_id=f"pb:form:{plot_id}",
                                        style=discord.ButtonStyle.primary, row=2))
        if names:
            view.add_item(discord.ui.Button(label=t(lang, "reset"), custom_id=f"pb:reset:{plot_id}",
                                            style=discord.ButtonStyle.secondary, row=2))
        # Clicks are routed by custom_id in on_interaction, so they keep working after a restart.
        view.stop()
        return view

    async def redraw(self, interaction: discord.Interaction, row: PlotRow, spec: PlotSpec, state: dict) -> None:
        """Re-render after a parameter change and edit the original message in place."""
        await interaction.response.defer()
        try:
            file = await self.render(spec)
        except asyncio.TimeoutError:
            await interaction.followup.send(t(row.lang, "timeout"), ephemeral=True)
            return
        except RenderError as exc:
            await interaction.followup.send(t(row.lang, "render_error", error=exc), ephemeral=True)
            return
        self.store.update(row.id, spec_json=spec.to_json(), state=state)
        await interaction.edit_original_response(
            embed=self.embed(spec, state, row.lang, file.filename), attachments=[file],
            view=self.view(row.id, spec, state, row.lang),
        )

    # ------------------------------------------------------------------ components

    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.type is not discord.InteractionType.component:
            return
        custom_id = (interaction.data or {}).get("custom_id", "")
        if not custom_id.startswith("pb:"):
            return
        _, action, plot_id = custom_id.split(":", 2)
        row = self.store.get(plot_id)
        if row is None:
            lang = self.lang_for(interaction)
            await interaction.response.send_message(t(lang, "expired"), ephemeral=True)
            return
        if self.cfg.owner_only and interaction.user.id != row.user_id:
            await interaction.response.send_message(t(row.lang, "not_owner"), ephemeral=True)
            return
        lock = self.locks.setdefault(plot_id, asyncio.Lock())
        async with lock:
            spec, state = PlotSpec.from_json(row.spec_json), row.state
            if action == "form":
                await interaction.response.send_modal(ParamModal(self, row, spec, state))
                return
            if action == "sel":
                state["selected"] = interaction.data["values"][0]
                self.store.update(row.id, state=state)
                await interaction.response.edit_message(view=self.view(row.id, spec, state, row.lang))
                return
            if action == "reset":
                spec.params = dict(state["initial"])
            elif action in ("dec2", "dec", "inc", "inc2"):
                name = state["selected"]
                factor = {"dec2": -5, "dec": -1, "inc": 1, "inc2": 5}[action]
                value = spec.params[name] + factor * state["steps"][name]
                spec.params[name] = round(value, 10)
            await self.redraw(interaction, row, spec, state)


class ParamModal(discord.ui.Modal):
    """Pop-up form: exact values for up to four parameters plus the first axis range."""

    def __init__(self, bot: PlotBot, row: PlotRow, spec: PlotSpec, state: dict) -> None:
        super().__init__(title=t(row.lang, "form_title"), timeout=600)
        self.bot, self.row, self.spec, self.state = bot, row, spec, state
        self.fields: dict[str, discord.ui.TextInput] = {}
        names = sorted(spec.params, key=lambda n: (n != state.get("selected"), n))[:4]
        for n in names:
            self.fields[n] = discord.ui.TextInput(label=pretty(n), default=f"{spec.params[n]:g}", max_length=40)
        self.axis = axis = spec.axes[0]
        a, b = spec.ranges[axis]
        self.fields["__range"] = discord.ui.TextInput(label=t(row.lang, "range_label", axis=pretty(axis))[:45],
                                                      default=f"{a:g}..{b:g}", max_length=60)
        for item in self.fields.values():
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        lang = self.row.lang
        try:
            for name, field in self.fields.items():
                if name == "__range":
                    lo_txt, _, hi_txt = field.value.replace(",", "..").partition("..")
                    lo, hi = number(lo_txt), number(hi_txt.lstrip("."))
                    if not (lo < hi and max(abs(lo), abs(hi)) <= MAX_ABS):
                        raise ValueError(field.value)
                    self.spec.ranges[self.axis] = [lo, hi]
                else:
                    value = number(field.value)
                    if not math.isfinite(value) or abs(value) > MAX_ABS:
                        raise ValueError(field.value)
                    self.spec.params[name] = value
        except (ValueError, MathParseError) as exc:
            await interaction.response.send_message(t(lang, "bad_value", value=str(exc)[:80]), ephemeral=True)
            return
        await self.bot.redraw(interaction, self.row, self.spec, self.state)


# ---------------------------------------------------------------------- slash commands


def _register_commands(bot: PlotBot) -> None:
    tree = bot.tree

    @tree.command(name="plot", description="Draw a formula or a description / Построить график")
    @app_commands.describe(prompt="Math (LaTeX or plain) or a description / Формула или описание")
    async def plot(interaction: discord.Interaction, prompt: app_commands.Range[str, 1, 1500]) -> None:
        await interaction.response.defer(thinking=True)
        lang = bot.lang_for(interaction, prompt)
        try:
            spec, explanation = await bot.make_spec(prompt)
        except MathParseError as exc:
            key = "parse_error" if bot.translator.enabled or looks_like_math(prompt) else "nl_disabled"
            await interaction.edit_original_response(content=t(lang, key, error=exc))
            return
        except Exception as exc:  # Claude API errors, declined requests
            log.warning("translation failed: %s", exc)
            await interaction.edit_original_response(content=t(lang, "nl_error", error=exc))
            return
        try:
            file = await bot.render(spec)
        except asyncio.TimeoutError:
            await interaction.edit_original_response(content=t(lang, "timeout"))
            return
        except RenderError as exc:
            await interaction.edit_original_response(content=t(lang, "render_error", error=exc))
            return

        plot_id = secrets.token_hex(6)
        names = sorted(spec.params)
        state = {
            "selected": names[0] if names else None,
            "steps": {n: _step(v) for n, v in spec.params.items()},
            "initial": dict(spec.params),
            "explanation": explanation,
        }
        now = time.time()
        bot.store.add(PlotRow(plot_id, interaction.guild_id, interaction.channel_id, None, interaction.user.id,
                              lang, prompt, spec.to_json(), state, now, now))
        message = await interaction.followup.send(
            embed=bot.embed(spec, state, lang, file.filename), file=file,
            view=bot.view(plot_id, spec, state, lang), wait=True,
        )
        bot.store.update(plot_id, message_id=message.id)

    @tree.command(name="tex", description="Render LaTeX text and math / Отобразить LaTeX")
    @app_commands.describe(source="Text with $math$, or a bare formula / Текст с $формулами$")
    async def tex(interaction: discord.Interaction, source: app_commands.Range[str, 1, 1500]) -> None:
        await interaction.response.defer(thinking=True)
        lang = bot.lang_for(interaction, source)
        loop = asyncio.get_running_loop()
        try:
            data = await asyncio.wait_for(
                loop.run_in_executor(bot.pool, render_tex, source.replace("\\n", "\n"), bot.cfg.usetex),
                bot.cfg.render_timeout,
            )
        except (TexError, asyncio.TimeoutError) as exc:
            await interaction.edit_original_response(content=t(lang, "tex_error", error=str(exc) or "timeout"))
            return
        await interaction.followup.send(file=discord.File(io.BytesIO(data), filename="tex.png"))

    @tree.command(name="language", description="Bot language / Язык бота")
    @app_commands.choices(lang=[app_commands.Choice(name="English", value="en"),
                                app_commands.Choice(name="Русский", value="ru")])
    async def language(interaction: discord.Interaction, lang: app_commands.Choice[str]) -> None:
        bot.store.set_lang(interaction.user.id, lang.value)
        await interaction.response.send_message(t(lang.value, "lang_set"), ephemeral=True)

    @tree.command(name="help", description="How to use the plot bot / Справка")
    async def help_(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(t(bot.lang_for(interaction), "help"), ephemeral=True)


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = Config.from_env()
    if not cfg.discord_token:
        raise SystemExit("DISCORD_TOKEN is not set (see .env.example)")
    if not cfg.anthropic_api_key:
        log.warning("ANTHROPIC_API_KEY is not set: only typed math will work, not natural language")
    PlotBot(cfg).run(cfg.discord_token, log_handler=None)
