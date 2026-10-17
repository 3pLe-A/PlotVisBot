import pytest

from plotbot.mathparse import parse_math
from plotbot.render import RenderError, render, render_json
from plotbot.texcard import TexError, render_tex

PNG = b"\x89PNG"
GIF = b"GIF8"


@pytest.mark.parametrize("text", [
    "x^2 + y^2 + z^2 = 25", r"x(t) = A e^{-\lambda_1 t} + B e^{-\lambda_2 t}", "r = 1 + cos(theta)",
    "z = x^2 - y^2", "z = r^2 sin(theta)", "r = 1 + 0.3 sin(3 theta) sin(4 phi)", "(cos t, sin t, t/5)",
    "x = cos(3t), y = sin(2t)", "(cos(u) sin(v), sin(u) sin(v), cos(v))", "y^2 = x^3 - x", "y = tan(x)",
    "y = 3",
])
def test_static(text):
    data, name = render(parse_math(text))
    assert name == "plot.png" and data.startswith(PNG)


@pytest.mark.parametrize("text", [
    "u(x,t) = sin(x - c t)", "u = exp(-(x^2+y^2)/(1+t)) cos(omega t)", "x^2 + y^2 + z^2 = (2 + sin(t))^2",
    "r = 1 + 0.3 sin(t) sin(3 theta) sin(4 phi)", "morph(x^2 + y^2 = 4, abs(x) + abs(y) = 2)",
])
def test_animated(text):
    data, name = render_json(parse_math(text).to_json())
    assert name == "plot.gif" and data.startswith(GIF) and len(data) < 10 * 1024 * 1024


def test_no_real_values():
    with pytest.raises(RenderError):
        render(parse_math("y = sqrt(-1 - x^2)"))


def test_surface_out_of_range():
    with pytest.raises(RenderError):
        render(parse_math("x^2 + y^2 + z^2 = 400"))


def test_tex_cyrillic_and_math():
    assert render_tex(r"Решение: $x(t) = A e^{-\lambda t}$").startswith(PNG)
    assert render_tex(r"\int_0^1 x^2\,dx = \frac{1}{3}").startswith(PNG)


def test_tex_errors():
    with pytest.raises(TexError):
        render_tex(r"$\frac{1}{$")
    with pytest.raises(TexError):
        render_tex(r"\input{/etc/passwd}", usetex=True)
