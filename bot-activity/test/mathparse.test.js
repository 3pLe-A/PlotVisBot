import { test } from "node:test";
import assert from "node:assert/strict";
import { parseMath, looksLikeMath, MathParseError, compile } from "../client/src/mathparse.js";

const CASES = {
  "x^2 + y^2 + z^2 = 25": "implicit3d",
  "x[t] = A*exp[-\\lambda_1 t] + B*exp[-\\lambda_2 t]": "explicit2d",
  "x(t) = A e^{-\\lambda_1 t} + B e^{-\\lambda_2 t}": "explicit2d",
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
  "\\frac{x^2}{a^2} + \\frac{y^2}{b^2} = 1": "implicit2d",
  "x² + y² = 4": "implicit2d",
  "Sin[x]": "explicit2d",
  "r = 2 + sin(3 theta) sin(phi)": "spherical",
};

for (const [text, kind] of Object.entries(CASES)) {
  test(`kind of ${text}`, () => assert.equal(parseMath(text).kind, kind));
}

test("ODE parameters, ranges and LaTeX", () => {
  const spec = parseMath("x(t) = A e^{-\\lambda_1 t} + B e^{-\\lambda_2 t}, A=2, B=-1, t in [0, 5]");
  assert.deepEqual(spec.params, { A: 2, B: -1, lambda_1: 1, lambda_2: 1 });
  assert.deepEqual(spec.ranges, { t: [0, 5] });
  assert.match(spec.latex, /\\lambda_\{1\}/);
  const f = compile(spec, spec.exprs[0]);
  assert.ok(Math.abs(f({ ...spec.params, t: 1 }) - (2 * Math.exp(-1) - Math.exp(-1))) < 1e-12);
});

test("assignment before formula and range forms", () => {
  assert.deepEqual(parseMath("k = 3; y = sin(k x)").params, { k: 3 });
  assert.deepEqual(parseMath("y = x, x = -1..2").ranges.x, [-1, 2]);
});

for (const bad of ["__import__('os')", "eval(1)", "x.constructor", "import({})", "createUnit(x)",
  "evaluate(x)", "parse(x)", "y = x; process"]) {
  test(`rejects ${bad}`, () => assert.throws(() => parseMath(bad), MathParseError));
}

test("detection", () => {
  assert.ok(looksLikeMath("x^2 + y^2 = \\frac{1}{2}"));
  assert.ok(!looksLikeMath("plot a damped oscillator"));
  assert.ok(!looksLikeMath("нарисуй сферу радиуса 5"));
});
