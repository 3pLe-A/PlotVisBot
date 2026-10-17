import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parseMath, looksLikeMath, MathParseError, compile } from "../client/src/mathparse.js";

// Shared with bot, so both parsers classify input the same way.
const SHARED = JSON.parse(readFileSync(new URL("../../shared/parser-cases.json", import.meta.url), "utf8"));
const CASES = { ...SHARED.kinds, "r = 2 + sin(3 theta) sin(phi)": "spherical" };

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

for (const bad of [...SHARED.rejects, "x.constructor", "createUnit(x)", "evaluate(x)", "parse(x)"]) {
  test(`rejects ${bad}`, () => assert.throws(() => parseMath(bad), MathParseError));
}

test("detection", () => {
  assert.ok(looksLikeMath("x^2 + y^2 = \\frac{1}{2}"));
  assert.ok(!looksLikeMath("plot a damped oscillator"));
  assert.ok(!looksLikeMath("нарисуй сферу радиуса 5"));
});
