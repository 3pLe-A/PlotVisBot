import json
from pathlib import Path

import pytest

from plotbot.mathparse import MathParseError, looks_like_math, parse_math

# Shared with activity-type, so both parsers classify input the same way.
SHARED = json.loads((Path(__file__).resolve().parents[2] / "shared" / "parser-cases.json").read_text(encoding="utf-8"))
CASES = SHARED["kinds"]


@pytest.mark.parametrize("text,kind", CASES.items())
def test_kinds(text, kind):
    assert parse_math(text).kind == kind


def test_ode_parameters_and_ranges():
    spec = parse_math(r"x(t) = A e^{-\lambda_1 t} + B e^{-\lambda_2 t}, A=2, B=-1, t in [0, 5]")
    assert spec.params == {"A": 2.0, "B": -1.0, "lamda_1": 1.0, "lamda_2": 1.0}
    assert spec.ranges == {"t": [0.0, 5.0]}
    assert spec.axes == ["t"] and spec.dep == "x"
    assert r"\lambda_{1}" in spec.latex


def test_assignment_before_formula():
    spec = parse_math("k = 3; y = sin(k x)")
    assert spec.params == {"k": 3.0}


def test_range_forms():
    assert parse_math("y = x, x = -1..2").ranges["x"] == [-1.0, 2.0]
    assert parse_math("y = x, 0 < x < pi").ranges["x"][1] == pytest.approx(3.14159, 1e-4)


@pytest.mark.parametrize("bad", SHARED["rejects"] + ["lambda: 1", "getattr(x, y)", "y = x; import os"])
def test_rejects_code(bad):
    with pytest.raises(MathParseError):
        parse_math(bad)


def test_detection():
    assert looks_like_math(r"x^2 + y^2 = \frac{1}{2}")
    assert not looks_like_math("plot a damped oscillator")
    assert not looks_like_math("нарисуй сферу радиуса 5")


def test_roundtrip_json():
    from plotbot.spec import PlotSpec

    spec = parse_math("u(x,t) = A sin(x - c t), A=2")
    again = PlotSpec.from_json(spec.to_json())
    assert again.exprs == spec.exprs and again.params == spec.params and again.time == "t"
