"""Render LaTeX text and math (English or Russian) to a PNG card.

Default engine: Matplotlib mathtext (no TeX install needed; text is any Unicode,
math goes between $...$). With PLOTBOT_USETEX=1 and a TeX distribution
installed, real LaTeX is used with amsmath and Cyrillic (T2A + babel) support.
"""

from __future__ import annotations

import io
import re
import shutil

import matplotlib

matplotlib.use("Agg")
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from .render import SURFACE, TEXT  # noqa: E402

MAX_TEX = 1500
USETEX_PREAMBLE = (
    r"\usepackage[T2A]{fontenc}\usepackage[utf8]{inputenc}"
    r"\usepackage[russian,english]{babel}\usepackage{amsmath,amssymb}"
)
# Commands that read/write files or redefine TeX itself are refused in usetex mode.
_FORBIDDEN = re.compile(
    r"\\(input|include|openin|openout|read|write|immediate|catcode|csname|def|edef|gdef|xdef|let|"
    r"newcommand|renewcommand|usepackage|special|directlua|loop|expandafter|jobname|endinput|makeatletter)\b"
)


class TexError(ValueError):
    pass


def _check(source: str) -> str:
    source = source.strip()
    if not source:
        raise TexError("empty")
    if len(source) > MAX_TEX:
        raise TexError("too long")
    return source


def _wrap_math(source: str) -> str:
    """A bare formula without $ is treated as display math."""
    return source if "$" in source else f"${source}$"


def render_tex(source: str, usetex: bool = False) -> bytes:
    source = _wrap_math(_check(source))
    if usetex and _FORBIDDEN.search(source):
        raise TexError("command not allowed")
    use_real = usetex and shutil.which("latex") is not None
    lines = source.split("\n")
    fig = Figure(figsize=(8, 0.6 + 0.55 * len(lines)), dpi=150)
    FigureCanvasAgg(fig)
    fig.patch.set_facecolor(SURFACE)
    rc = {"text.usetex": True, "text.latex.preamble": USETEX_PREAMBLE} if use_real else {}
    try:
        with matplotlib.rc_context(rc):
            for i, line in enumerate(lines):
                fig.text(0.03, 1 - (i + 0.8) / (len(lines) + 0.4), line, color=TEXT, fontsize=16, va="center")
            buf = io.BytesIO()
            fig.savefig(buf, format="png", facecolor=SURFACE, bbox_inches="tight", pad_inches=0.25)
    except Exception as exc:  # mathtext ParseException, LaTeX RuntimeError
        msg = str(exc).strip().splitlines()
        raise TexError(msg[-1] if msg else "invalid LaTeX") from exc
    return buf.getvalue()
