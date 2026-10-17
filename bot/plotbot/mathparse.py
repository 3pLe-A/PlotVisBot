"""Turn user math (plain, Mathematica-style or LaTeX) into a PlotSpec.

Untrusted text never reaches ``eval`` unchecked: every identifier is checked
against a whitelist first, and the SymPy parser runs with an empty
``__builtins__``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import sympy as sp
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_application,
    implicit_multiplication,
    parse_expr,
    standard_transformations,
)

from .spec import PlotSpec

MAX_INPUT = 600

# Coordinate symbols. Everything else that is free becomes a slider parameter.
COORDS = ("x", "y", "z", "t", "r", "theta", "phi")
DEFAULT_RANGES = {
    "x": (-6.0, 6.0),
    "y": (-6.0, 6.0),
    "z": (-6.0, 6.0),
    "t": (0.0, 10.0),
    "r": (0.0, 5.0),
    "theta": (0.0, 2 * 3.141592653589793),
    "phi": (0.0, 2 * 3.141592653589793),
    "u": (0.0, 2 * 3.141592653589793),
    "v": (0.0, 3.141592653589793),
    "s": (0.0, 10.0),
}

FUNCTIONS = {
    "sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "cot": sp.cot, "sec": sp.sec, "csc": sp.csc,
    "asin": sp.asin, "acos": sp.acos, "atan": sp.atan, "atan2": sp.atan2,
    "arcsin": sp.asin, "arccos": sp.acos, "arctan": sp.atan,
    "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh, "coth": sp.coth,
    "asinh": sp.asinh, "acosh": sp.acosh, "atanh": sp.atanh,
    "exp": sp.exp, "log": sp.log, "ln": sp.log, "sqrt": sp.sqrt, "abs": sp.Abs,
    "sign": sp.sign, "floor": sp.floor, "ceil": sp.ceiling, "erf": sp.erf,
    "heaviside": sp.Heaviside, "besselj": sp.besselj, "min": sp.Min, "max": sp.Max,
}
CONSTANTS = {"pi": sp.pi, "e": sp.E, "E": sp.E}

GREEK = (
    "alpha beta gamma delta epsilon zeta eta theta iota kappa lamda lambda mu nu xi "
    "omicron pi rho sigma tau upsilon phi chi psi omega"
).split()
GREEK_UNICODE = dict(zip(
    "αβγδεζηθικλμνξοπρστυφχψωϕϑΔΩΓΦΨΛΣΘ",
    "alpha beta gamma delta epsilon zeta eta theta iota kappa lamda mu nu xi omicron pi rho "
    "sigma tau upsilon phi chi psi omega phi theta Delta Omega Gamma Phi Psi Lamda Sigma Theta".split(),
))

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SYMBOL_NAME = re.compile(r"^(?:[A-Za-z]\d*|(?:%s)\d*)(?:_[A-Za-z0-9]+)?$" % "|".join(GREEK + [g.capitalize() for g in GREEK]))
_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|[-+]?pi(?:/\d+)?|[-+]?\d*\s*\*?\s*pi(?:/\d+)?"

TRANSFORMS = standard_transformations + (implicit_multiplication, implicit_application, convert_xor)


class MathParseError(ValueError):
    """Input could not be read as mathematics."""


@dataclass
class Item:
    """One parsed clause: an equation ``lhs = rhs`` or a bare expression."""

    lhs: sp.Expr | None
    rhs: sp.Expr
    dep: str | None = None  # dependent name when the LHS is a plain symbol or f(args)
    tuple_: tuple[sp.Expr, ...] | None = None
    tex: str = ""  # display form, when it differs from lhs = rhs (morph)


# --------------------------------------------------------------------------- text normalisation


def _braced(s: str, i: int) -> tuple[str, int]:
    """Return the content of the brace group starting at s[i] == '{' and the index after it."""
    if i >= len(s) or s[i] != "{":
        # single-token argument, e.g. \frac12
        return s[i], i + 1
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1 : j], j + 1
    raise MathParseError("unbalanced braces")


def latex_to_plain(s: str) -> str:
    """Convert the common subset of LaTeX math into plain notation."""
    s = s.replace("$", "")
    for a, b in ((r"\left", ""), (r"\right", ""), (r"\cdot", "*"), (r"\times", "*"),
                 (r"\,", " "), (r"\;", " "), (r"\!", ""), (r"\quad", " "), (r"\dfrac", r"\frac"),
                 (r"\tfrac", r"\frac"), (r"\mathrm", ""), (r"\operatorname", ""), (r"\in", " in "),
                 (r"\leq", "<="), (r"\le", "<="), (r"\geq", ">="), (r"\ge", ">="), (r"\infty", "oo")):
        s = s.replace(a, b)
    out, i = [], 0
    while i < len(s):
        if s.startswith(r"\frac", i):
            num, i = _braced(s, i + 5)
            den, i = _braced(s, i)
            out.append(f"(({latex_to_plain(num)})/({latex_to_plain(den)}))")
        elif s.startswith(r"\sqrt", i):
            i += 5
            n = None
            if i < len(s) and s[i] == "[":
                j = s.index("]", i)
                n, i = s[i + 1 : j], j + 1
            arg, i = _braced(s, i)
            arg = latex_to_plain(arg)
            out.append(f"sqrt({arg})" if n is None else f"(({arg})**(1/({n})))")
        elif s[i] == "\\":
            m = _IDENT.match(s, i + 1)
            if not m:
                i += 1
                continue
            name = m.group(0)
            out.append(" " + ("lamda" if name == "lambda" else name) + " ")
            i = m.end()
        else:
            out.append(s[i])
            i += 1
    s = "".join(out)
    s = re.sub(r"_\{\s*([A-Za-z0-9]+)\s*\}", r"_\1", s)
    return s.replace("{", "(").replace("}", ")")


def normalise(text: str) -> str:
    """Unicode, LaTeX and Mathematica notation to one plain dialect."""
    s = text.strip().strip("`").strip()
    if len(s) > MAX_INPUT:
        raise MathParseError("input too long")
    for a, b in (("−", "-"), ("–", "-"), ("·", "*"), ("×", "*"), ("÷", "/"), ("²", "^2"), ("³", "^3"),
                 ("√", "sqrt"), ("∞", "oo"), ("≤", "<="), ("≥", ">="), ("∈", " in "), ("π", " pi ")):
        s = s.replace(a, b)
    for g, name in GREEK_UNICODE.items():
        s = s.replace(g, f" {name} ")
    if "\\" in s or "$" in s or "{" in s:  # e^{-0.2 t} is LaTeX even without a backslash
        s = latex_to_plain(s)
    # Mathematica: Exp[x] -> exp(x), x[t] -> x(t); Pi, E constants
    s = re.sub(r"\b([A-Z][a-z]+)\[", lambda m: m.group(1).lower() + "[", s)
    s = re.sub(r"\bPi\b", "pi", s)
    s = _call_brackets(s)
    s = re.sub(r"\blambda\b", "lamda", s)
    s = re.sub(r"\blambda_", "lamda_", s)
    return s


def _call_brackets(s: str) -> str:
    """Mathematica calls f[x] -> f(x); range brackets such as `in [0, 1]` stay."""
    out, stack = list(s), []
    for i, ch in enumerate(s):
        if ch == "[":
            j = i - 1
            while j >= 0 and s[j] == " ":
                j -= 1
            is_call = j >= 0 and (s[j].isalnum() or s[j] == "_") and not s[: j + 1].rstrip().endswith(" in")
            stack.append(is_call)
            if is_call:
                out[i] = "("
        elif ch == "]" and stack and stack.pop():
            out[i] = ")"
    return "".join(out)


# --------------------------------------------------------------------------- clause splitting


def _split_top(s: str) -> list[str]:
    """Split on ; , newlines and 'where/with/где/при' at bracket depth 0."""
    s = re.sub(r"\b(where|with|for|где|при)\b", ";", s, flags=re.IGNORECASE)
    parts, depth, cur = [], 0, []
    for ch in s:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if depth == 0 and ch in ";,\n":
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


_RANGE_IN = re.compile(r"^([A-Za-z]\w*)\s+in\s*[\[(]\s*(.+?)\s*,\s*(.+?)\s*[\])]$")
_RANGE_DOTS = re.compile(r"^([A-Za-z]\w*)\s*=\s*(.+?)\s*\.\.\s*(.+)$")
_RANGE_CHAIN = re.compile(r"^(.+?)\s*<=?\s*([A-Za-z]\w*)\s*<=?\s*(.+)$")


def number(text: str) -> float:
    """Evaluate a constant such as `2`, `-1.5` or `pi/2`."""
    expr = _parse(text)
    if expr.free_symbols:
        raise MathParseError(f"not a number: {text}")
    return float(sp.N(expr))


# --------------------------------------------------------------------------- safe expression parser


def _symbol_name(name: str) -> str:
    return "lamda" + name[6:] if name.startswith("lambda") else name


def _check_identifiers(s: str) -> dict[str, object]:
    local: dict[str, object] = {}
    for m in _IDENT.finditer(s):
        name = m.group(0)
        if name in FUNCTIONS:
            local[name] = FUNCTIONS[name]
        elif name in CONSTANTS:
            local[name] = CONSTANTS[name]
        elif name == "oo":
            local[name] = sp.oo
        elif _SYMBOL_NAME.match(name):
            local[name] = sp.Symbol(_symbol_name(name), real=True)
        elif re.fullmatch(r"[a-z]{2,3}", name) and all(c in "xyzt" for c in name):
            # "xy" -> x*y
            continue
        else:
            raise MathParseError(f"unknown name: {name}")
    return local


_SAFE_GLOBALS: dict[str, object] = {}
exec("from sympy import Symbol, Integer, Float, Rational, Function", _SAFE_GLOBALS)  # noqa: S102 - fixed text
_SAFE_GLOBALS["__builtins__"] = {}


def _parse(text: str) -> sp.Expr:
    text = text.strip()
    if not text:
        raise MathParseError("empty expression")
    if re.search(r"[^\w\s+\-*/^().,<>=!]", text) or "__" in text or "." in re.sub(r"\d\.\d|\d\.|\.\d", "", text):
        raise MathParseError(f"unsupported characters in: {text}")
    text = re.sub(r"\b([xyzt]{2,3})\b", lambda m: "*".join(m.group(1)), text)
    local = _check_identifiers(text)
    try:
        expr = parse_expr(text, local_dict=local, global_dict=dict(_SAFE_GLOBALS), transformations=TRANSFORMS)
    except Exception as exc:  # SyntaxError, TypeError, TokenError ...
        raise MathParseError(f"cannot parse: {text}") from exc
    if not isinstance(expr, sp.Basic):
        raise MathParseError(f"cannot parse: {text}")
    return sp.sympify(expr)


def _parse_tuple(text: str) -> tuple[sp.Expr, ...] | None:
    m = re.fullmatch(r"\(\s*(.+)\s*\)", text)
    if not m:
        return None
    inner, depth, parts, cur = m.group(1), 0, [], []
    for ch in inner:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return None
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    if len(parts) < 2:
        return None
    return tuple(_parse(p) for p in parts)


_DEP = re.compile(r"^([A-Za-z]\w*)\s*(?:\(\s*([A-Za-z]\w*(?:\s*,\s*[A-Za-z]\w*)*)\s*\))?$")


def _parse_item(clause: str) -> Item:
    if "=" in clause and not re.search(r"[<>!]=|==", clause):
        lhs_txt, rhs_txt = clause.split("=", 1)
        lhs_txt, rhs_txt = lhs_txt.strip(), rhs_txt.strip()
        tup = _parse_tuple(rhs_txt)
        m = _DEP.match(lhs_txt)
        if m and (m.group(2) or not (FUNCTIONS.keys() & {m.group(1)})):
            name = _symbol_name(m.group(1))
            if tup:
                return Item(None, tup[0], dep=name, tuple_=tup)
            return Item(sp.Symbol(name, real=True), _parse(rhs_txt), dep=name)
        return Item(_parse(lhs_txt), _parse(rhs_txt))
    tup = _parse_tuple(clause)
    if tup:
        return Item(None, tup[0], tuple_=tup)
    return Item(None, _parse(clause))


# --------------------------------------------------------------------------- classification


def _names(expr: sp.Expr) -> set[str]:
    return {s.name for s in expr.free_symbols}


def parse_math(text: str) -> PlotSpec:
    """Parse plain/LaTeX/Mathematica math into a PlotSpec, or raise MathParseError."""
    s = normalise(text)
    ranges: dict[str, tuple[float, float]] = {}
    params: dict[str, float] = {}
    items: list[Item] = []
    morph = False
    for clause in _split_top(s):
        if m := _RANGE_IN.match(clause) or _RANGE_DOTS.match(clause):
            ranges[_symbol_name(m.group(1))] = (number(m.group(2)), number(m.group(3)))
            continue
        if (m := _RANGE_CHAIN.match(clause)) and "=" not in clause.replace("<=", ""):
            ranges[_symbol_name(m.group(2))] = (number(m.group(1)), number(m.group(3)))
            continue
        if m := _MORPH.match(clause):
            items.append(_morph_item(m.group(1)))
            morph = True
            continue
        items.append(_parse_item(clause))
    consts = [it for it in items
              if it.dep and it.dep not in COORDS and it.tuple_ is None and not it.rhs.free_symbols]
    if len(consts) < len(items):
        for it in consts:
            params[it.dep] = float(sp.N(it.rhs))
        items = [it for it in items if it not in consts]
    if not items:
        raise MathParseError("nothing to plot")
    spec = _classify(items)
    spec.latex = items[0].tex if morph and len(items) == 1 else _latex(items, spec)
    if morph:
        ranges.setdefault("t", (0.0, 1.0))
    for name in spec.coord_names():
        if name in ranges:
            continue
        lo, hi = DEFAULT_RANGES.get(name, (-6.0, 6.0))
        if spec.kind in ("spherical",) and name == "theta":
            lo, hi = 0.0, 3.141592653589793
        ranges[name] = (lo, hi)
    for p in sorted(spec.param_names()):
        spec.params.setdefault(p, params.get(p, 1.0))
    for p, v in params.items():
        if p in spec.params:
            spec.params[p] = v
    spec.ranges = {k: [float(a), float(b)] for k, (a, b) in ranges.items() if k in spec.coord_names()}
    spec.source = text.strip()
    return spec


def _classify(items: list[Item]) -> PlotSpec:
    # Parametric: a tuple, or x = f(t), y = g(t)[, z = h(t)]
    if len(items) == 1 and items[0].tuple_:
        return _parametric(list(items[0].tuple_), dep=items[0].dep)
    deps = [it.dep for it in items]
    if len(items) in (2, 3) and deps[: len(items)] == ["x", "y", "z"][: len(items)]:
        return _parametric([it.rhs for it in items])
    if len(items) > 1:
        raise MathParseError("several equations: only parametric x=…, y=…[, z=…] is supported")

    it = items[0]
    if it.lhs is None:  # bare expression -> pick a dependent name
        names = _names(it.rhs) & set(COORDS)
        dep = {frozenset({"theta"}): "r", frozenset({"x", "y"}): "z", frozenset({"r", "theta"}): "z"}.get(
            frozenset(names), "y" if names <= {"x"} else "u")
        if names == {"t"}:
            dep = "x"
        it = Item(sp.Symbol(dep, real=True), it.rhs, dep=dep)

    if it.dep and it.dep not in _names(it.rhs):
        return _explicit(it.dep, it.rhs)
    return _implicit(it.lhs - it.rhs)


def _explicit(dep: str, rhs: sp.Expr) -> PlotSpec:
    v = _names(rhs) & set(COORDS)
    v.discard(dep)
    key = frozenset(v)
    # A shape that changes in time: the same kind as without t, with t as time.
    time = "t" if "t" in key and key != {"t"} else None
    space = key - {"t"}
    if dep == "r" and key <= {"theta"} or (time and dep == "r" and space == {"theta"}):
        return PlotSpec(kind="polar", exprs=[rhs], axes=["theta"], dep="r", time=time)
    if dep == "r" and space in ({"theta", "phi"}, {"phi"}):
        return PlotSpec(kind="spherical", exprs=[rhs], axes=["theta", "phi"], dep="r", time=time)
    if space == {"r", "theta"} or key == {"r"}:
        return PlotSpec(kind="cylindrical", exprs=[rhs], axes=["r", "theta"], dep=dep, time=time)
    if key in ({"x", "t"}, {"r", "t"}):
        a = "x" if "x" in key else "r"
        return PlotSpec(kind="anim1d", exprs=[rhs], axes=[a], time="t", dep=dep)
    if key == {"x", "y", "t"}:
        return PlotSpec(kind="anim2d", exprs=[rhs], axes=["x", "y"], time="t", dep=dep)
    if len(key) == 2 and "t" not in key:
        return PlotSpec(kind="explicit3d", exprs=[rhs], axes=sorted(key, key=COORDS.index), dep=dep)
    if len(key) <= 1:
        axis = next(iter(key)) if key else ("t" if dep == "x" else "x")
        return PlotSpec(kind="explicit2d", exprs=[rhs], axes=[axis], dep=dep)
    raise MathParseError("too many independent variables")


def _to_cartesian(expr: sp.Expr, three_d: bool | None = None) -> sp.Expr:
    x, y, z = (sp.Symbol(n, real=True) for n in "xyz")
    names = _names(expr)
    sub = {}
    if three_d is None:
        three_d = "phi" in names
    if "r" in names or "theta" in names or "phi" in names:
        if three_d:  # spherical, physics convention: theta polar, phi azimuth
            rr = sp.sqrt(x**2 + y**2 + z**2)
            sub = {sp.Symbol("r", real=True): rr, sp.Symbol("theta", real=True): sp.acos(z / rr),
                   sp.Symbol("phi", real=True): sp.atan2(y, x)}
        else:
            sub = {sp.Symbol("r", real=True): sp.sqrt(x**2 + y**2), sp.Symbol("theta", real=True): sp.atan2(y, x)}
    return expr.subs(sub)


def _implicit(f: sp.Expr) -> PlotSpec:
    f = _to_cartesian(f)
    v = _names(f) & set(COORDS)
    time = "t" if "t" in v else None
    v.discard("t")
    if v <= {"x", "y"}:
        return PlotSpec(kind="implicit2d", exprs=[f], axes=["x", "y"], time=time)
    if v <= {"x", "y", "z"}:
        return PlotSpec(kind="implicit3d", exprs=[f], axes=["x", "y", "z"], time=time)
    raise MathParseError("cannot tell which coordinates this equation uses")


_MORPH = re.compile(r"^morph\s*\((.+)\)$", re.IGNORECASE)


def _morph_item(inner: str) -> Item:
    """morph(F1, F2): the figure F1 turns into F2 as t goes from 0 to 1.

    Both figures become implicit functions F = lhs - rhs, and the plot is the
    level set (1 - t) F1 + t F2 = 0.
    """
    parts = _split_top(inner)
    if len(parts) != 2:
        raise MathParseError("morph needs two figures: morph(F1, F2)")
    sides = []
    for part in parts:
        it = _parse_item(part)
        if it.tuple_ is not None:
            raise MathParseError("morph works with equations, not parametric forms")
        sides.append(it.rhs if it.lhs is None else it.lhs - it.rhs)
    three_d = any(_names(f) & {"z", "phi"} for f in sides)
    f1, f2 = (_to_cartesian(f, three_d) for f in sides)
    t = sp.Symbol("t", real=True)
    tex = rf"(1 - t)\left[{sp.latex(f1)}\right] + t\left[{sp.latex(f2)}\right] = 0"
    return Item((1 - t) * f1 + t * f2, sp.Integer(0), tex=tex)


def _parametric(comps: list[sp.Expr], dep: str | None = None) -> PlotSpec:
    if len(comps) not in (2, 3):
        raise MathParseError("parametric form needs 2 or 3 components")
    names = set().union(*(_names(c) for c in comps))
    if {"u", "v"} <= names and len(comps) == 3:
        return PlotSpec(kind="surface3d", exprs=comps, axes=["u", "v"], time="t" if "t" in names else None)
    kind = "parametric2d" if len(comps) == 2 else "parametric3d"
    if {"s", "t"} <= names:  # curve parameter s, time t
        return PlotSpec(kind=kind, exprs=comps, axes=["s"], time="t")
    for p in ("t", "s", "u", "theta", "phi"):
        if p in names:
            return PlotSpec(kind=kind, exprs=comps, axes=[p])
    raise MathParseError("parametric form needs a parameter t (or s, u)")


def _latex(items: list[Item], spec: PlotSpec) -> str:
    def lhs(it: Item) -> str:
        if it.dep is None:
            return sp.latex(it.lhs) if it.lhs is not None else ""
        args = spec.axes + ([spec.time] if spec.time else [])
        head = sp.latex(sp.Symbol(it.dep))
        if spec.kind in ("explicit2d", "anim1d", "anim2d", "explicit3d") and spec.dep not in ("y", "z"):
            head += r"\left(" + ", ".join(sp.latex(sp.Symbol(a)) for a in args) + r"\right)"
        return head

    parts = []
    for it in items:
        if it.tuple_:
            body = r"\left(" + ", ".join(sp.latex(c) for c in it.tuple_) + r"\right)"
            parts.append(f"{lhs(it)} = {body}" if it.dep else body)
        elif it.lhs is None:
            parts.append(f"{sp.latex(sp.Symbol(spec.dep or 'y'))} = {sp.latex(it.rhs)}")
        else:
            parts.append(f"{lhs(it)} = {sp.latex(it.rhs)}")
    return r",\quad ".join(parts)


# --------------------------------------------------------------------------- detection


_WORD = re.compile(r"[A-Za-zА-Яа-яЁё]{4,}")
_KNOWN_WORDS = set(FUNCTIONS) | set(GREEK) | {"lambda", "where", "with", "frac", "sqrt", "left", "right",
                                              "cdot", "times", "quad", "infty", "dfrac", "tfrac", "mathrm",
                                              "operatorname", "lamda", "morph"}


def looks_like_math(text: str) -> bool:
    """Cheap test: no prose words and contains an operator or '='."""
    words = [w for w in _WORD.findall(text) if w.lower() not in _KNOWN_WORDS]
    return not words and bool(re.search(r"[=^*/+\-\\(]", text))
