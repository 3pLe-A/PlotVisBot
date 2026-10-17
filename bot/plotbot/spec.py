"""PlotSpec: everything needed to redraw a plot, serialisable to JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import sympy as sp

KINDS = (
    "explicit2d",   # y = f(x)
    "implicit2d",   # F(x, y) = 0
    "polar",        # r = f(theta)
    "parametric2d", # (x(t), y(t))
    "explicit3d",   # z = f(x, y)
    "cylindrical",  # z = f(r, theta)
    "spherical",    # r = f(theta, phi)
    "implicit3d",   # F(x, y, z) = 0
    "parametric3d", # (x(t), y(t), z(t))
    "surface3d",    # (x(u,v), y(u,v), z(u,v))
    "anim1d",       # u(x, t): 1D + time
    "anim2d",       # u(x, y, t): 2D + time
)


@dataclass
class PlotSpec:
    kind: str
    exprs: list[sp.Expr]
    axes: list[str]
    dep: str | None = None
    time: str | None = None
    ranges: dict[str, list[float]] = field(default_factory=dict)
    params: dict[str, float] = field(default_factory=dict)
    latex: str = ""
    source: str = ""

    def coord_names(self) -> list[str]:
        return self.axes + ([self.time] if self.time else [])

    def param_names(self) -> set[str]:
        free = set().union(*(e.free_symbols for e in self.exprs))
        return {s.name for s in free} - set(self.coord_names())

    @property
    def animated(self) -> bool:
        return self.time is not None

    def to_json(self) -> str:
        return json.dumps({
            "kind": self.kind,
            "exprs": [sp.srepr(e) for e in self.exprs],
            "axes": self.axes,
            "dep": self.dep,
            "time": self.time,
            "ranges": self.ranges,
            "params": self.params,
            "latex": self.latex,
            "source": self.source,
        })

    @classmethod
    def from_json(cls, text: str) -> "PlotSpec":
        """Rebuild from JSON written by to_json (trusted: it comes from our own database)."""
        d = json.loads(text)
        d["exprs"] = [sp.sympify(e) for e in d["exprs"]]
        return cls(**d)
