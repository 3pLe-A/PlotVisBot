"""Render a PlotSpec to PNG (static) or GIF (animated) bytes with Matplotlib.

Only the object-oriented Matplotlib API is used (no pyplot), so rendering is
safe to run in worker threads.
"""

from __future__ import annotations

import io
import warnings

import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import numpy as np  # noqa: E402
import sympy as sp  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from PIL import Image  # noqa: E402

from .spec import PlotSpec  # noqa: E402

# Dark chart surface (Discord's default theme) and the reference palette's dark steps.
SURFACE = "#1a1a19"
TEXT = "#f0efec"
TEXT_2 = "#c3c2b7"
GRID = "#3a3a37"
SERIES = ["#3987e5", "#d95926", "#199e70"]
SEQ = LinearSegmentedColormap.from_list("seq", ["#0d2a4d", "#1f5fa8", "#3987e5", "#8fc0f5", "#e3f0ff"])
DIV = LinearSegmentedColormap.from_list("div", ["#3987e5", "#9fc3ef", "#8a8a85", "#f0a382", "#d95926"])

FRAMES = 40
FRAMES_3D = 30   # 3D frames cost ~0.3-0.8 s each; keeps a GIF under the render timeout
LIMIT_SAMPLES = 8
FRAME_MS = 90
DPI = 110


class RenderError(ValueError):
    """The expression could not be evaluated or drawn."""


def _style(fig: Figure) -> None:
    fig.patch.set_facecolor(SURFACE)


def _style_ax(ax, three_d: bool = False) -> None:
    ax.set_facecolor(SURFACE)
    ax.tick_params(colors=TEXT_2, labelsize=9)
    for label in (ax.xaxis.label, ax.yaxis.label):
        label.set_color(TEXT_2)
    if three_d:
        ax.zaxis.label.set_color(TEXT_2)
        for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
            axis.set_pane_color((0.12, 0.12, 0.115, 1.0))
            axis._axinfo["grid"]["color"] = GRID
        return
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.grid(True, color=GRID, linewidth=0.6)


def _sym_tex(name: str) -> str:
    return sp.latex(sp.Symbol(name))


def _title(fig: Figure, spec: PlotSpec, extra: str = "") -> None:
    formula = f"${spec.latex}$" if spec.latex else spec.source
    try:
        # Validate mathtext before committing it to the figure.
        matplotlib.mathtext.MathTextParser("path").parse(formula)
    except Exception:
        formula = spec.source
    fig.suptitle(formula, color=TEXT, fontsize=13, y=0.975)
    params = ",  ".join(f"${_sym_tex(k)} = {v:g}$" for k, v in sorted(spec.params.items()))
    sub = "   ".join(p for p in (params, extra) if p)
    if sub:
        fig.text(0.5, 0.875, sub, ha="center", color=TEXT_2, fontsize=10)


def _func(spec: PlotSpec, expr: sp.Expr, args: list[str]):
    expr = expr.subs({sp.Symbol(k, real=True): v for k, v in spec.params.items()})
    syms = [sp.Symbol(a, real=True) for a in args]
    leftover = expr.free_symbols - set(syms)
    if leftover:
        raise RenderError("unassigned symbols: " + ", ".join(sorted(s.name for s in leftover)))
    f = sp.lambdify(syms, expr, modules=[{"Heaviside": lambda x, h=0.5: np.heaviside(x, 0.5)}, "numpy"])

    def call(*arrays):
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore")
            out = f(*arrays)
        out = np.asarray(out, dtype=complex if np.iscomplexobj(out) else float)
        if np.iscomplexobj(out):
            out = np.where(np.abs(out.imag) < 1e-9, out.real, np.nan)
        shape = np.broadcast(*arrays).shape if arrays else ()
        out = np.broadcast_to(out, shape).astype(float)
        out[~np.isfinite(out)] = np.nan
        return out

    return call


def _robust_limits(values: np.ndarray) -> tuple[float, float]:
    v = values[np.isfinite(values)]
    if v.size == 0:
        raise RenderError("the function has no real values in this range")
    lo, hi = float(v.min()), float(v.max())
    p1, p99 = np.percentile(v, [1, 99])
    if hi - lo > 20 * max(p99 - p1, 1e-12):  # poles: clip to the bulk of the data
        lo, hi = float(p1), float(p99)
    if hi - lo < 1e-9:
        lo, hi = lo - 1, hi + 1
    pad = 0.06 * (hi - lo)
    return lo - pad, hi + pad


def _rng(spec: PlotSpec, name: str) -> tuple[float, float]:
    a, b = spec.ranges[name]
    return float(a), float(b)


def _png(fig: Figure) -> bytes:
    buf = io.BytesIO()
    FigureCanvasAgg(fig)
    fig.savefig(buf, format="png", dpi=DPI, facecolor=SURFACE)
    return buf.getvalue()


def _equal_3d(ax, xs, ys, zs) -> None:
    pts = [np.asarray(a)[np.isfinite(a)] for a in (xs, ys, zs)]
    if any(p.size == 0 for p in pts):
        raise RenderError("the surface has no real points in this range")
    ax.set_box_aspect((np.ptp(pts[0]) or 1, np.ptp(pts[1]) or 1, np.ptp(pts[2]) or 1))


# --------------------------------------------------------------------------- static kinds


def _explicit2d(fig, spec):
    a = spec.axes[0]
    lo, hi = _rng(spec, a)
    xs = np.linspace(lo, hi, 1500)
    ys = _func(spec, spec.exprs[0], [a])(xs)
    ylo, yhi = _robust_limits(ys)
    jumps = np.abs(np.diff(ys)) > (yhi - ylo)  # break the line at poles such as tan(x)
    ys[1:][jumps] = np.nan
    ax = fig.add_subplot(111)
    _style_ax(ax)
    ax.plot(xs, ys, color=SERIES[0], linewidth=2)
    ax.set_ylim(ylo, yhi)
    ax.set_xlim(lo, hi)
    ax.set_xlabel(f"${_sym_tex(a)}$")
    ax.set_ylabel(f"${_sym_tex(spec.dep or 'y')}$")


def _implicit2d(fig, spec):
    (x0, x1), (y0, y1) = _rng(spec, "x"), _rng(spec, "y")
    X, Y = np.meshgrid(np.linspace(x0, x1, 500), np.linspace(y0, y1, 500))
    F = _func(spec, spec.exprs[0], ["x", "y"])(X, Y)
    if not (np.nanmin(F) <= 0 <= np.nanmax(F)):
        raise RenderError("the curve does not cross this range")
    ax = fig.add_subplot(111)
    _style_ax(ax)
    ax.contour(X, Y, F, levels=[0], colors=[SERIES[0]], linewidths=2)
    ax.set_aspect("equal")
    ax.set_xlabel("$x$")
    ax.set_ylabel("$y$")


def _polar(fig, spec):
    lo, hi = _rng(spec, "theta")
    th = np.linspace(lo, hi, 2000)
    r = _func(spec, spec.exprs[0], ["theta"])(th)
    ax = fig.add_subplot(111, projection="polar")
    ax.set_facecolor(SURFACE)
    ax.tick_params(colors=TEXT_2, labelsize=9)
    ax.grid(True, color=GRID)
    ax.spines["polar"].set_color(GRID)
    ax.set_rlabel_position(22.5)
    ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(4))
    ax.plot(th, r, color=SERIES[0], linewidth=2)


def _parametric2d(fig, spec):
    p = spec.axes[0]
    lo, hi = _rng(spec, p)
    ts = np.linspace(lo, hi, 3000)
    xs, ys = (_func(spec, e, [p])(ts) for e in spec.exprs)
    ax = fig.add_subplot(111)
    _style_ax(ax)
    ax.plot(xs, ys, color=SERIES[0], linewidth=2)
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("$x$")
    ax.set_ylabel("$y$")


def _surface(fig, spec, X, Y, Z, labels=("x", "y", "z")):
    ax = fig.add_subplot(111, projection="3d")
    _style_ax(ax, three_d=True)
    Zm = np.ma.masked_invalid(Z)
    ax.plot_surface(X, Y, Zm, cmap=SEQ, linewidth=0, antialiased=True, rstride=1, cstride=1)
    ax.set_xlabel(f"${labels[0]}$")
    ax.set_ylabel(f"${labels[1]}$")
    ax.set_zlabel(f"${labels[2]}$")
    return ax


def _explicit3d(fig, spec):
    a, b = spec.axes
    (x0, x1), (y0, y1) = _rng(spec, a), _rng(spec, b)
    X, Y = np.meshgrid(np.linspace(x0, x1, 90), np.linspace(y0, y1, 90))
    Z = _func(spec, spec.exprs[0], [a, b])(X, Y)
    lo, hi = _robust_limits(Z)
    Z = np.where((Z < lo) | (Z > hi), np.nan, Z)
    ax = _surface(fig, spec, X, Y, Z, (_sym_tex(a), _sym_tex(b), _sym_tex(spec.dep or "z")))
    ax.set_zlim(lo, hi)


def _cylindrical(fig, spec):
    (r0, r1), (t0, t1) = _rng(spec, "r"), _rng(spec, "theta")
    R, T = np.meshgrid(np.linspace(r0, r1, 70), np.linspace(t0, t1, 120))
    Z = _func(spec, spec.exprs[0], ["r", "theta"])(R, T)
    _surface(fig, spec, R * np.cos(T), R * np.sin(T), Z, ("x", "y", _sym_tex(spec.dep or "z")))


def _spherical(fig, spec):
    (t0, t1), (p0, p1) = _rng(spec, "theta"), _rng(spec, "phi")
    T, P = np.meshgrid(np.linspace(t0, t1, 90), np.linspace(p0, p1, 160))
    R = _func(spec, spec.exprs[0], ["theta", "phi"])(T, P)
    X, Y, Z = R * np.sin(T) * np.cos(P), R * np.sin(T) * np.sin(P), R * np.cos(T)
    ax = _surface(fig, spec, X, Y, Z)
    _equal_3d(ax, X, Y, Z)


def _surface3d(fig, spec):
    (u0, u1), (v0, v1) = _rng(spec, "u"), _rng(spec, "v")
    U, V = np.meshgrid(np.linspace(u0, u1, 120), np.linspace(v0, v1, 80))
    X, Y, Z = (_func(spec, e, ["u", "v"])(U, V) for e in spec.exprs)
    ax = _surface(fig, spec, X, Y, Z)
    _equal_3d(ax, X, Y, Z)


def _parametric3d(fig, spec):
    p = spec.axes[0]
    lo, hi = _rng(spec, p)
    ts = np.linspace(lo, hi, 3000)
    xs, ys, zs = (_func(spec, e, [p])(ts) for e in spec.exprs)
    ax = fig.add_subplot(111, projection="3d")
    _style_ax(ax, three_d=True)
    ax.plot(xs, ys, zs, color=SERIES[0], linewidth=2)
    ax.set_xlabel("$x$")
    ax.set_ylabel("$y$")
    ax.set_zlabel("$z$")


def _implicit3d(fig, spec):
    from skimage.measure import marching_cubes

    n = 72
    (x0, x1), (y0, y1), (z0, z1) = (_rng(spec, a) for a in "xyz")
    xs, ys, zs = np.linspace(x0, x1, n), np.linspace(y0, y1, n), np.linspace(z0, z1, n)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    F = _func(spec, spec.exprs[0], ["x", "y", "z"])(X, Y, Z)
    finite = F[np.isfinite(F)]
    if finite.size == 0 or not (finite.min() <= 0 <= finite.max()):
        raise RenderError("the surface does not cross this range")
    F = np.where(np.isfinite(F), F, np.nanmax(F))
    verts, faces, _, _ = marching_cubes(F, level=0.0, spacing=((x1 - x0) / (n - 1), (y1 - y0) / (n - 1), (z1 - z0) / (n - 1)))
    verts += np.array([x0, y0, z0])
    ax = fig.add_subplot(111, projection="3d")
    _style_ax(ax, three_d=True)
    ax.plot_trisurf(verts[:, 0], verts[:, 1], faces, verts[:, 2], cmap=SEQ, linewidth=0, antialiased=True)
    ax.set_xlabel("$x$")
    ax.set_ylabel("$y$")
    ax.set_zlabel("$z$")
    _equal_3d(ax, verts[:, 0], verts[:, 1], verts[:, 2])


STATIC = {
    "explicit2d": _explicit2d, "implicit2d": _implicit2d, "polar": _polar, "parametric2d": _parametric2d,
    "explicit3d": _explicit3d, "cylindrical": _cylindrical, "spherical": _spherical,
    "surface3d": _surface3d, "parametric3d": _parametric3d, "implicit3d": _implicit3d,
}


# --------------------------------------------------------------------------- animated kinds


def _frames_to_gif(frames: list[Image.Image]) -> bytes:
    buf = io.BytesIO()
    pal = [f.convert("RGB").quantize(colors=128, method=Image.Quantize.MEDIANCUT) for f in frames]
    pal[0].save(buf, format="GIF", save_all=True, append_images=pal[1:], duration=FRAME_MS, loop=0, optimize=True)
    return buf.getvalue()


def _grab(fig: Figure) -> Image.Image:
    canvas = fig.canvas
    canvas.draw()
    return Image.frombuffer("RGBA", canvas.get_width_height(), canvas.buffer_rgba()).copy()


def _anim1d(fig, spec) -> bytes:
    a, tname = spec.axes[0], spec.time
    (x0, x1), (t0, t1) = _rng(spec, a), _rng(spec, tname)
    xs, ts = np.linspace(x0, x1, 600), np.linspace(t0, t1, 240)
    f = _func(spec, spec.exprs[0], [a, tname])
    XT = f(xs[None, :], ts[:, None])
    lo, hi = _robust_limits(XT)

    ax1 = fig.add_axes([0.1, 0.11, 0.48, 0.7])
    ax2 = fig.add_axes([0.66, 0.11, 0.3, 0.7])
    _style_ax(ax1)
    _style_ax(ax2)
    ax2.grid(False)
    line, = ax1.plot([], [], color=SERIES[0], linewidth=2)
    ax1.set_xlim(x0, x1)
    ax1.set_ylim(lo, hi)
    ax1.set_xlabel(f"${_sym_tex(a)}$")
    ax1.set_ylabel(f"${_sym_tex(spec.dep or 'u')}$")
    vmax = max(abs(lo), abs(hi))
    signed = lo < 0 < hi
    ax2.imshow(np.clip(XT, lo, hi), aspect="auto", origin="lower", extent=(x0, x1, t0, t1),
               cmap=DIV if signed else SEQ, vmin=-vmax if signed else lo, vmax=vmax if signed else hi)
    ax2.set_xlabel(f"${_sym_tex(a)}$")
    ax2.set_ylabel(f"${_sym_tex(tname)}$")
    ax2.set_title("spacetime", color=TEXT_2, fontsize=9)
    now = ax2.axhline(t0, color=TEXT, linewidth=1.2)
    label = ax1.text(0.02, 0.95, "", transform=ax1.transAxes, color=TEXT, fontsize=10, va="top")

    frames = []
    for t in np.linspace(t0, t1, FRAMES):
        line.set_data(xs, f(xs, np.full_like(xs, t)))
        now.set_ydata([t, t])
        label.set_text(f"${_sym_tex(tname)} = {t:.2f}$")
        frames.append(_grab(fig))
    return _frames_to_gif(frames)


def _anim2d(fig, spec) -> bytes:
    tname = spec.time
    (x0, x1), (y0, y1), (t0, t1) = _rng(spec, "x"), _rng(spec, "y"), _rng(spec, tname)
    X, Y = np.meshgrid(np.linspace(x0, x1, 160), np.linspace(y0, y1, 160))
    f = _func(spec, spec.exprs[0], ["x", "y", tname])
    times = np.linspace(t0, t1, FRAMES)
    fields = [f(X, Y, np.full_like(X, t)) for t in times]
    lo, hi = _robust_limits(np.stack(fields))
    signed = lo < 0 < hi
    vmax = max(abs(lo), abs(hi))

    ax = fig.add_axes([0.12, 0.1, 0.7, 0.72])
    _style_ax(ax)
    ax.grid(False)
    im = ax.imshow(fields[0], origin="lower", extent=(x0, x1, y0, y1), cmap=DIV if signed else SEQ,
                   vmin=-vmax if signed else lo, vmax=vmax if signed else hi, aspect="equal")
    cax = fig.add_axes([0.85, 0.1, 0.025, 0.72])
    cb = fig.colorbar(im, cax=cax)
    cb.ax.tick_params(colors=TEXT_2, labelsize=8)
    cb.outline.set_edgecolor(GRID)
    ax.set_xlabel("$x$")
    ax.set_ylabel("$y$")
    label = ax.text(0.02, 0.97, "", transform=ax.transAxes, color=TEXT, fontsize=10, va="top")

    frames = []
    for t, field in zip(times, fields):
        im.set_data(field)
        label.set_text(f"${_sym_tex(tname)} = {t:.2f}$")
        frames.append(_grab(fig))
    return _frames_to_gif(frames)


ANIMATED = {"anim1d": _anim1d, "anim2d": _anim2d}
THREE_D = {"explicit3d", "cylindrical", "spherical", "surface3d", "parametric3d", "implicit3d"}
EQUAL_ASPECT = {"spherical", "surface3d", "implicit3d"}


def _frame(spec: PlotSpec, t: float, limits=None) -> Figure:
    """Draw a static kind at one moment, with the time variable fixed to t."""
    fig = Figure(figsize=(8, 5.2), dpi=DPI)
    FigureCanvasAgg(fig)
    _style(fig)
    _title(fig, spec, f"${_sym_tex(spec.time)} = {t:.2f}$")
    at_t = PlotSpec(kind=spec.kind, exprs=spec.exprs, axes=spec.axes, dep=spec.dep, ranges=spec.ranges,
                    params={**spec.params, spec.time: float(t)})
    STATIC[spec.kind](fig, at_t)
    fig.subplots_adjust(top=0.82)
    if limits:
        ax = fig.axes[0]
        if spec.kind not in THREE_D and ax.get_aspect() != "auto":
            ax.set_adjustable("box")
        ax.set_xlim(*limits[0])
        ax.set_ylim(*limits[1])
        if spec.kind in THREE_D:
            ax.set_zlim(*limits[2])
            if spec.kind in EQUAL_ASPECT:
                ax.set_box_aspect([hi - lo for lo, hi in limits])
    return fig


def _limits(ax) -> list[tuple[float, float]]:
    lims = [ax.get_xlim(), ax.get_ylim()]
    if hasattr(ax, "get_zlim"):
        lims.append(ax.get_zlim())
    return lims


def _animate_shape(spec: PlotSpec) -> bytes:
    """A shape that changes in time: one static drawing per frame, on fixed axes."""
    t0, t1 = _rng(spec, spec.time)
    times = np.linspace(t0, t1, FRAMES_3D if spec.kind in THREE_D else FRAMES)
    # Axis limits from a few sample moments, so the axes don't jump between frames.
    seen = []
    for t in np.linspace(t0, t1, LIMIT_SAMPLES):
        try:
            seen.append(_limits(_frame(spec, t).axes[0]))
        except RenderError:
            continue
    if not seen:
        raise RenderError("nothing to draw at any moment in this time range")
    limits = [(min(s[i][0] for s in seen), max(s[i][1] for s in seen)) for i in range(len(seen[0]))]
    frames = []
    for t in times:
        try:
            fig = _frame(spec, t, limits)
        except RenderError:
            fig = Figure(figsize=(8, 5.2), dpi=DPI)
            FigureCanvasAgg(fig)
            _style(fig)
            _title(fig, spec, f"${_sym_tex(spec.time)} = {t:.2f}$")
            fig.text(0.5, 0.45, "no real points at this moment", ha="center", color=TEXT_2, fontsize=11)
        frames.append(_grab(fig))
    return _frames_to_gif(frames)


def render(spec: PlotSpec) -> tuple[bytes, str]:
    """Return (image bytes, file name)."""
    fig = Figure(figsize=(8, 5.2), dpi=DPI)
    FigureCanvasAgg(fig)
    _style(fig)
    try:
        _title(fig, spec)
        if spec.kind in ANIMATED:
            return ANIMATED[spec.kind](fig, spec), "plot.gif"
        if spec.time:
            return _animate_shape(spec), "plot.gif"
        STATIC[spec.kind](fig, spec)
        if spec.kind not in ("anim1d", "anim2d"):
            fig.subplots_adjust(top=0.82)
        return _png(fig), "plot.png"
    except RenderError:
        raise
    except (ValueError, TypeError, ZeroDivisionError, OverflowError, RuntimeError) as exc:
        raise RenderError(str(exc)) from exc


def render_json(spec_json: str) -> tuple[bytes, str]:
    """Process-pool entry point: rebuild the spec from JSON and render it."""
    return render(PlotSpec.from_json(spec_json))
