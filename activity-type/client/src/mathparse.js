// Turn user math (plain, Mathematica-style or LaTeX) into a plot spec.
// Expressions are parsed and evaluated by math.js, which runs in its own
// sandbox: no access to JavaScript globals, and import/createUnit are disabled.

import { create, all } from "mathjs";

export const math = create(all);
// Keep our own handle on the parser, then disable functions an expression could
// use to reach the parser or the namespace from inside (math.js security guidance).
const parse = math.parse;
math.import(
  {
    import() { throw new Error("import is disabled"); },
    createUnit() { throw new Error("createUnit is disabled"); },
    evaluate() { throw new Error("evaluate is disabled"); },
    parse() { throw new Error("parse is disabled"); },
    simplify() { throw new Error("simplify is disabled"); },
    derivative() { throw new Error("derivative is disabled"); },
    resolve() { throw new Error("resolve is disabled"); },
    heaviside: (x) => (x > 0 ? 1 : x < 0 ? 0 : 0.5),
    ln: (x) => Math.log(x),
  },
  { override: true },
);

export const MAX_INPUT = 600;
export const COORDS = ["x", "y", "z", "t", "r", "theta", "phi"];
const TAU = 2 * Math.PI;
export const DEFAULT_RANGES = {
  x: [-6, 6], y: [-6, 6], z: [-6, 6], t: [0, 10], r: [0, 5],
  theta: [0, TAU], phi: [0, TAU], u: [0, TAU], v: [0, Math.PI], s: [0, 10],
};
const CONSTANTS = new Set(["e", "E", "pi", "PI", "i", "Infinity", "NaN", "tau", "phi_golden"]);
const FUNCTIONS = new Set(
  ("sin cos tan cot sec csc asin acos atan atan2 sinh cosh tanh coth asinh acosh atanh exp log ln sqrt " +
    "abs sign floor ceil erf heaviside min max cbrt").split(" "),
);
const GREEK = ("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma " +
  "tau upsilon phi chi psi omega").split(" ");
const GREEK_UNICODE = {
  α: "alpha", β: "beta", γ: "gamma", δ: "delta", ε: "epsilon", ζ: "zeta", η: "eta", θ: "theta", ι: "iota",
  κ: "kappa", λ: "lambda", μ: "mu", ν: "nu", ξ: "xi", π: "pi", ρ: "rho", σ: "sigma", τ: "tau", υ: "upsilon",
  φ: "phi", ϕ: "phi", χ: "chi", ψ: "psi", ω: "omega", Δ: "Delta", Ω: "Omega", Γ: "Gamma", Φ: "Phi", Λ: "Lambda",
};
const SYMBOL_NAME = new RegExp(`^(?:[A-Za-z]\\d*|(?:${GREEK.join("|")}|${GREEK.map(cap).join("|")})\\d*)(?:_[A-Za-z0-9]+)?$`);

export class MathParseError extends Error {}

function cap(s) { return s[0].toUpperCase() + s.slice(1); }

// --------------------------------------------------------------------------- normalisation

function braced(s, i) {
  if (s[i] !== "{") return [s[i] ?? "", i + 1];
  let depth = 0;
  for (let j = i; j < s.length; j++) {
    if (s[j] === "{") depth++;
    else if (s[j] === "}" && --depth === 0) return [s.slice(i + 1, j), j + 1];
  }
  throw new MathParseError("unbalanced braces");
}

export function latexToPlain(src) {
  let s = src.replaceAll("$", "");
  for (const [a, b] of [["\\left", ""], ["\\right", ""], ["\\cdot", "*"], ["\\times", "*"], ["\\,", " "],
    ["\\;", " "], ["\\!", ""], ["\\quad", " "], ["\\dfrac", "\\frac"], ["\\tfrac", "\\frac"], ["\\mathrm", ""],
    ["\\operatorname", ""], ["\\in", " in "], ["\\leq", "<="], ["\\le", "<="], ["\\geq", ">="], ["\\ge", ">="]]) {
    s = s.replaceAll(a, b);
  }
  let out = "";
  let i = 0;
  while (i < s.length) {
    if (s.startsWith("\\frac", i)) {
      let num, den;
      [num, i] = braced(s, i + 5);
      [den, i] = braced(s, i);
      out += `((${latexToPlain(num)})/(${latexToPlain(den)}))`;
    } else if (s.startsWith("\\sqrt", i)) {
      i += 5;
      let n = null;
      if (s[i] === "[") {
        const j = s.indexOf("]", i);
        n = s.slice(i + 1, j);
        i = j + 1;
      }
      let arg;
      [arg, i] = braced(s, i);
      arg = latexToPlain(arg);
      out += n === null ? `sqrt(${arg})` : `((${arg})^(1/(${n})))`;
    } else if (s[i] === "\\") {
      const m = /^[A-Za-z]+/.exec(s.slice(i + 1));
      if (!m) { i++; continue; }
      i += 1 + m[0].length;
      out += ` ${m[0]}${s[i] === "_" ? "" : " "}`;
    } else {
      out += s[i++];
    }
  }
  return out.replace(/_\{\s*([A-Za-z0-9]+)\s*\}/g, "_$1").replaceAll("{", "(").replaceAll("}", ")");
}

function callBrackets(s) {
  // Mathematica calls f[x] -> f(x); range brackets such as `in [0, 1]` stay.
  const out = s.split("");
  const stack = [];
  for (let i = 0; i < s.length; i++) {
    if (s[i] === "[") {
      const before = s.slice(0, i).trimEnd();
      const isCall = /[A-Za-z0-9_]$/.test(before) && !/\bin$/.test(before);
      stack.push(isCall);
      if (isCall) out[i] = "(";
    } else if (s[i] === "]" && stack.length && stack.pop()) {
      out[i] = ")";
    }
  }
  return out.join("");
}

export function normalise(text) {
  let s = text.trim().replace(/^`+|`+$/g, "").trim();
  if (s.length > MAX_INPUT) throw new MathParseError("input too long");
  for (const [a, b] of [["−", "-"], ["–", "-"], ["·", "*"], ["×", "*"], ["÷", "/"], ["²", "^2"], ["³", "^3"],
    ["√", "sqrt"], ["≤", "<="], ["≥", ">="], ["∈", " in "]]) s = s.replaceAll(a, b);
  for (const [g, name] of Object.entries(GREEK_UNICODE)) s = s.replaceAll(g, ` ${name} `);
  if (s.includes("\\") || s.includes("$")) s = latexToPlain(s);
  s = s.replace(/\b([A-Z][a-z]+)\[/g, (_, f) => `${f.toLowerCase()}[`).replace(/\bPi\b/g, "pi");
  s = callBrackets(s);
  // "cos t" -> "cos(t)"
  s = s.replace(new RegExp(`\\b(${[...FUNCTIONS].join("|")})\\s+([A-Za-z0-9_.]+)`, "g"), "$1($2)");
  // "3t" -> "3 t" is handled by math.js implicit multiplication; "xy" -> "x y"
  s = s.replace(/\b([xyzt]{2,3})\b/g, (m) => m.split("").join(" "));
  return s;
}

// --------------------------------------------------------------------------- clauses

function splitTop(src) {
  const s = src.replace(/\b(where|with|for)\b|(?:^|\s)(где|при)(?=\s)/gi, ";");
  const parts = [];
  let depth = 0;
  let cur = "";
  for (const ch of s) {
    if ("([".includes(ch)) depth++;
    else if (")]".includes(ch)) depth--;
    if (depth === 0 && ";,\n".includes(ch)) { parts.push(cur); cur = ""; } else cur += ch;
  }
  parts.push(cur);
  return parts.map((p) => p.trim()).filter(Boolean);
}

function checkIdentifiers(text) {
  if (/[^\w\s+\-*/^().<>=!]/.test(text) || text.includes("__")) {
    throw new MathParseError(`unsupported characters in: ${text}`);
  }
  for (const [name] of text.matchAll(/[A-Za-z_][A-Za-z0-9_]*/g)) {
    if (FUNCTIONS.has(name) || CONSTANTS.has(name) || SYMBOL_NAME.test(name)) continue;
    throw new MathParseError(`unknown name: ${name}`);
  }
}

export function parseExpr(text) {
  const t = text.trim();
  if (!t) throw new MathParseError("empty expression");
  checkIdentifiers(t);
  try {
    return parse(t);
  } catch (e) {
    throw new MathParseError(`cannot parse: ${t}`);
  }
}

export function number(text) {
  const node = parseExpr(text);
  if (freeSymbols(node).size) throw new MathParseError(`not a number: ${text}`);
  const v = node.compile().evaluate({});
  if (typeof v !== "number" || !Number.isFinite(v)) throw new MathParseError(`not a number: ${text}`);
  return v;
}

export function freeSymbols(node) {
  const out = new Set();
  node.traverse((c, path, parent) => {
    if (c.isSymbolNode && !(parent && parent.isFunctionNode && parent.fn === c) && !CONSTANTS.has(c.name)) {
      out.add(c.name);
    }
  });
  return out;
}

function parseTuple(text) {
  const m = /^\(\s*([\s\S]+)\s*\)$/.exec(text);
  if (!m) return null;
  const parts = [];
  let depth = 0;
  let cur = "";
  for (const ch of m[1]) {
    if (ch === "(") depth++;
    else if (ch === ")" && --depth < 0) return null;
    if (ch === "," && depth === 0) { parts.push(cur); cur = ""; } else cur += ch;
  }
  parts.push(cur);
  return parts.length >= 2 ? parts.map(parseExpr) : null;
}

const DEP = /^([A-Za-z]\w*)\s*(?:\(\s*([A-Za-z]\w*(?:\s*,\s*[A-Za-z]\w*)*)\s*\))?$/;

function parseItem(clause) {
  if (clause.includes("=") && !/[<>!]=|==/.test(clause)) {
    const k = clause.indexOf("=");
    const lhs = clause.slice(0, k).trim();
    const rhs = clause.slice(k + 1).trim();
    const tup = parseTuple(rhs);
    const m = DEP.exec(lhs);
    if (m && (m[2] || !FUNCTIONS.has(m[1]))) {
      if (tup) return { lhs: null, rhs: tup[0], dep: m[1], tuple: tup };
      return { lhs: parse(m[1]), rhs: parseExpr(rhs), dep: m[1] };
    }
    return { lhs: parseExpr(lhs), rhs: parseExpr(rhs), dep: null };
  }
  const tup = parseTuple(clause);
  if (tup) return { lhs: null, rhs: tup[0], dep: null, tuple: tup };
  return { lhs: null, rhs: parseExpr(clause), dep: null };
}

// --------------------------------------------------------------------------- classification

const setEq = (a, b) => a.size === b.length && b.every((x) => a.has(x));
const coordsIn = (node) => new Set([...freeSymbols(node)].filter((n) => COORDS.includes(n)));

export function parseMath(text) {
  const s = normalise(text);
  const ranges = {};
  const assigned = {};
  let items = [];
  for (const clause of splitTop(s)) {
    let m = /^([A-Za-z]\w*)\s+in\s*[[(]\s*(.+?)\s*,\s*(.+?)\s*[\])]$/.exec(clause) ||
      /^([A-Za-z]\w*)\s*=\s*(.+?)\s*\.\.\s*(.+)$/.exec(clause);
    if (m) { ranges[m[1]] = [number(m[2]), number(m[3])]; continue; }
    m = /^(.+?)\s*<=?\s*([A-Za-z]\w*)\s*<=?\s*(.+)$/.exec(clause);
    if (m && !clause.replaceAll("<=", "").includes("=")) { ranges[m[2]] = [number(m[1]), number(m[3])]; continue; }
    items.push(parseItem(clause));
  }
  const consts = items.filter((it) => it.dep && !COORDS.includes(it.dep) && !it.tuple && freeSymbols(it.rhs).size === 0);
  if (consts.length < items.length) {
    for (const it of consts) assigned[it.dep] = it.rhs.compile().evaluate({});
    items = items.filter((it) => !consts.includes(it));
  }
  if (!items.length) throw new MathParseError("nothing to plot");

  const spec = classify(items);
  spec.latex = toLatex(items, spec);
  spec.source = text.trim();
  spec.ranges = {};
  for (const name of coordNames(spec)) {
    let r = ranges[name] ?? DEFAULT_RANGES[name] ?? [-6, 6];
    if (spec.kind === "spherical" && name === "theta" && !ranges[name]) r = [0, Math.PI];
    spec.ranges[name] = r;
  }
  spec.params = {};
  for (const p of [...paramNames(spec)].sort()) spec.params[p] = assigned[p] ?? 1;
  return spec;
}

export function coordNames(spec) {
  return spec.time ? [...spec.axes, spec.time] : [...spec.axes];
}

export function paramNames(spec) {
  const names = new Set();
  for (const e of spec.exprs) for (const n of freeSymbols(parse(e))) names.add(n);
  for (const c of coordNames(spec)) names.delete(c);
  return names;
}

function classify(items) {
  if (items.length === 1 && items[0].tuple) return parametric(items[0].tuple);
  const deps = items.map((it) => it.dep);
  if ((items.length === 2 || items.length === 3) && deps.join() === ["x", "y", "z"].slice(0, items.length).join()) {
    return parametric(items.map((it) => it.rhs));
  }
  if (items.length > 1) throw new MathParseError("several equations: only parametric x=…, y=…[, z=…] is supported");
  let it = items[0];
  if (!it.lhs) {
    const names = coordsIn(it.rhs);
    let dep = names.size === 0 || setEq(names, ["x"]) ? "y" : "u";
    if (setEq(names, ["theta"])) dep = "r";
    if (setEq(names, ["x", "y"]) || setEq(names, ["r", "theta"])) dep = "z";
    if (setEq(names, ["t"])) dep = "x";
    it = { lhs: parse(dep), rhs: it.rhs, dep, implicitDep: true };
    items[0] = it;
  }
  if (it.dep && !freeSymbols(it.rhs).has(it.dep)) return explicit(it.dep, it.rhs);
  return implicit(new math.OperatorNode("-", "subtract", [it.lhs, new math.ParenthesisNode(it.rhs)]));
}

function explicit(dep, rhs) {
  const v = coordsIn(rhs);
  v.delete(dep);
  const e = [rhs.toString()];
  if (dep === "r" && (v.size === 0 || setEq(v, ["theta"]))) return { kind: "polar", exprs: e, axes: ["theta"], dep };
  if (dep === "r" && (setEq(v, ["theta", "phi"]) || setEq(v, ["phi"]))) {
    return { kind: "spherical", exprs: e, axes: ["theta", "phi"], dep };
  }
  if (setEq(v, ["r", "theta"]) || setEq(v, ["r"])) return { kind: "cylindrical", exprs: e, axes: ["r", "theta"], dep };
  if (setEq(v, ["x", "t"]) || setEq(v, ["r", "t"])) {
    return { kind: "anim1d", exprs: e, axes: [v.has("x") ? "x" : "r"], time: "t", dep };
  }
  if (setEq(v, ["x", "y", "t"])) return { kind: "anim2d", exprs: e, axes: ["x", "y"], time: "t", dep };
  if (v.size === 2 && !v.has("t")) {
    return { kind: "explicit3d", exprs: e, axes: [...v].sort((a, b) => COORDS.indexOf(a) - COORDS.indexOf(b)), dep };
  }
  if (v.size <= 1) {
    const axis = v.size ? [...v][0] : dep === "x" ? "t" : "x";
    return { kind: "explicit2d", exprs: e, axes: [axis], dep };
  }
  throw new MathParseError("too many independent variables");
}

function toCartesian(node) {
  const names = freeSymbols(node);
  if (!names.has("r") && !names.has("theta") && !names.has("phi")) return node;
  const sub = names.has("phi")
    ? { r: "sqrt(x^2+y^2+z^2)", theta: "acos(z/sqrt(x^2+y^2+z^2))", phi: "atan2(y,x)" }
    : { r: "sqrt(x^2+y^2)", theta: "atan2(y,x)" };
  return node.transform((c) => (c.isSymbolNode && sub[c.name] ? new math.ParenthesisNode(parse(sub[c.name])) : c));
}

function implicit(f) {
  const g = toCartesian(f);
  const v = coordsIn(g);
  if ([...v].every((n) => n === "x" || n === "y")) return { kind: "implicit2d", exprs: [g.toString()], axes: ["x", "y"] };
  if ([...v].every((n) => "xyz".includes(n))) return { kind: "implicit3d", exprs: [g.toString()], axes: ["x", "y", "z"] };
  throw new MathParseError("implicit equations in time are not supported");
}

function parametric(comps) {
  if (comps.length !== 2 && comps.length !== 3) throw new MathParseError("parametric form needs 2 or 3 components");
  const names = new Set(comps.flatMap((c) => [...freeSymbols(c)]));
  const exprs = comps.map((c) => c.toString());
  if (names.has("u") && names.has("v") && comps.length === 3) return { kind: "surface3d", exprs, axes: ["u", "v"] };
  for (const p of ["t", "s", "u", "theta", "phi"]) {
    if (names.has(p)) return { kind: comps.length === 2 ? "parametric2d" : "parametric3d", exprs, axes: [p] };
  }
  throw new MathParseError("parametric form needs a parameter t (or s, u)");
}

// --------------------------------------------------------------------------- LaTeX

export function symbolTex(name) {
  const [base, sub] = name.split(/_(.+)/);
  const m = /^([A-Za-z]+?)(\d*)$/.exec(base);
  let head = base;
  let digits = "";
  if (m && (GREEK.includes(m[1]) || GREEK.map(cap).includes(m[1]))) { head = `\\${m[1]}`; digits = m[2]; }
  else if (m && m[1].length === 1) { head = m[1]; digits = m[2]; }
  const subscript = [digits, sub].filter(Boolean).join(",");
  return subscript ? `${head}_{${subscript}}` : head;
}

const TEX_FUNCS = { erf: "\\operatorname{erf}", heaviside: "H", sign: "\\operatorname{sgn}", ln: "\\ln", atan2: "\\operatorname{atan2}" };

function nodeTex(node) {
  return node.toTex({
    implicit: "hide",
    parenthesis: "auto",
    handler(n, options) {
      if (n.isSymbolNode && !CONSTANTS.has(n.name)) return ` ${symbolTex(n.name)}`;
      if (n.isFunctionNode && TEX_FUNCS[n.fn.name]) {
        return `${TEX_FUNCS[n.fn.name]}\\left(${n.args.map((a) => a.toTex(options)).join(",")}\\right)`;
      }
      return undefined;
    },
  });
}

function toLatex(items, spec) {
  const head = (it) => {
    if (!it.dep) return it.lhs ? nodeTex(it.lhs) : "";
    let h = symbolTex(it.dep);
    if (["explicit2d", "anim1d", "anim2d", "explicit3d"].includes(spec.kind) && !["y", "z"].includes(spec.dep)) {
      h += `\\left(${coordNames(spec).map(symbolTex).join(", ")}\\right)`;
    }
    return h;
  };
  return items.map((it) => {
    if (it.tuple) {
      const body = `\\left(${it.tuple.map(nodeTex).join(", ")}\\right)`;
      return it.dep ? `${head(it)} = ${body}` : body;
    }
    return `${head(it)} = ${nodeTex(it.rhs)}`;
  }).join(",\\quad ");
}

const GREEK_CHAR = Object.fromEntries(Object.entries(GREEK_UNICODE).map(([c, n]) => [n, c]));
const SUBSCRIPT = "₀₁₂₃₄₅₆₇₈₉";

// lambda_1 -> λ₁, omega -> ω, A -> A (for plain-text labels).
export function pretty(name) {
  const [base, sub] = name.split(/_(.+)/);
  const head = GREEK_CHAR[base] ?? base;
  if (!sub) return head;
  return head + (/^\d+$/.test(sub) ? [...sub].map((d) => SUBSCRIPT[d]).join("") : `_${sub}`);
}

// --------------------------------------------------------------------------- detection

const KNOWN_WORDS = new Set([...FUNCTIONS, ...GREEK, "where", "with", "frac", "sqrt", "left", "right", "cdot",
  "times", "quad", "infty", "dfrac", "tfrac", "mathrm", "operatorname"]);

export function looksLikeMath(text) {
  const words = (text.match(/[A-Za-zА-Яа-яЁё]{4,}/g) || []).filter((w) => !KNOWN_WORDS.has(w.toLowerCase()));
  return words.length === 0 && /[=^*/+\-\\(]/.test(text);
}

// --------------------------------------------------------------------------- evaluation

export function compile(spec, expr) {
  const code = parse(expr).compile();
  return (scope) => {
    try {
      const v = code.evaluate(scope);
      return typeof v === "number" && Number.isFinite(v) ? v : NaN;
    } catch {
      return NaN;
    }
  };
}
