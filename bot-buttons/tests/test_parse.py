import pytest

from plotbot.mathparse import MathParseError, looks_like_math, parse_math

CASES = {
    "x^2 + y^2 + z^2 = 25": "implicit3d",
    r"x[t] = A*exp[-\lambda_1 t] + B*exp[-\lambda_2 t]": "explicit2d",
    r"x(t) = A e^{-\lambda_1 t} + B e^{-\lambda_2 t}": "explicit2d",
    "y = sin(k x)": "explicit2d",
    "sin(x)": "explicit2d",
    "r = 1 + cos(theta)": "polar",
    "z = x^2 - y^2": "explicit3d",
    "z = r^2 sin(theta)": "cylindrical",
    "r = 1 + 0.3 sin(3 theta) sin(4 phi)": "spherical",
    "u(x,t) = sin(x - c t)": "anim1d",
    "u = exp(-(x^2+y^2)/(1+t)) cos(omega t)": "anim2d",
    "(cos t, sin t, t/5)": "parametric3d",
    "x = cos(3t), y = sin(2t)": "parametric2d",
    "(cos(u) sin(v), sin(u) sin(v), cos(v))": "surface3d",
    r"\frac{x^2}{a^2} + \frac{y^2}{b^2} = 1": "implicit2d",
    "x² + y² = 4": "implicit2d",
    "Sin[x]": "explicit2d",
}


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


@pytest.mark.parametrize("bad", ["__import__('os')", "eval(1)", "x.real", "open(x)", "exec(x)", "lambda: 1",
                                 "().__class__", "getattr(x, y)", "y = x; import os"])
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
