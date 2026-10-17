// Build Plotly data + layout for a spec at given parameter values and time.

import { compile, pretty } from "./mathparse.js";

const N2 = 900;   // samples for curves
const NS = 70;    // grid for surfaces
const NI = 34;    // grid for implicit surfaces (NI^3 evaluations)
const NH = 140;   // grid for heatmaps

const linspace = (a, b, n) => Array.from({ length: n }, (_, i) => a + ((b - a) * i) / (n - 1));

export function theme() {
  const css = getComputedStyle(document.documentElement);
  const v = (name) => css.getPropertyValue(name).trim();
  return {
    surface: v("--surface-1"), text: v("--text-primary"), text2: v("--text-secondary"), grid: v("--grid"),
    series: v("--series-1"),
    seq: [[0, v("--seq-0")], [0.5, v("--seq-1")], [1, v("--seq-2")]],
    div: [[0, v("--div-neg")], [0.5, v("--div-mid")], [1, v("--div-pos")]],
  };
}

function robustRange(values) {
  const v = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!v.length) throw new Error("no real values in this range");
  let lo = v[0];
  let hi = v[v.length - 1];
  const p1 = v[Math.floor(0.01 * (v.length - 1))];
  const p99 = v[Math.floor(0.99 * (v.length - 1))];
  if (hi - lo > 20 * Math.max(p99 - p1, 1e-12)) { lo = p1; hi = p99; }
  if (hi - lo < 1e-9) { lo -= 1; hi += 1; }
  const pad = 0.06 * (hi - lo);
  return [lo - pad, hi + pad];
}

const label = (name) => pretty(name);

function axis2d(th, title, extra = {}) {
  return { title: { text: title }, color: th.text2, gridcolor: th.grid, zerolinecolor: th.grid, ...extra };
}

function axis3d(th, title) {
  return { title: { text: title }, color: th.text2, gridcolor: th.grid, zerolinecolor: th.grid,
    backgroundcolor: th.surface, showbackground: true };
}

function base(th, spec) {
  return {
    paper_bgcolor: th.surface, plot_bgcolor: th.surface, font: { color: th.text2, size: 12 },
    margin: { l: 56, r: 20, t: 16, b: 48 }, showlegend: false, uirevision: spec.source,
  };
}

// A cache per spec+params for data that does not depend on time (heatmaps, ranges).
const cache = new Map();
function cached(key, make) {
  if (!cache.has(key)) {
    if (cache.size > 20) cache.clear();
    cache.set(key, make());
  }
  return cache.get(key);
}

export function buildFigure(spec, params, time) {
  const th = theme();
  const f = spec.exprs.map((e) => compile(spec, e));
  const R = spec.ranges;
  const layout = base(th, spec);
  const key = JSON.stringify([spec.source, spec.ranges, params]);

  switch (spec.kind) {
    case "explicit2d": {
      const a = spec.axes[0];
      const xs = linspace(...R[a], N2);
      const ys = xs.map((x) => f[0]({ ...params, [a]: x }));
      const [lo, hi] = robustRange(ys);
      for (let i = 1; i < ys.length; i++) if (Math.abs(ys[i] - ys[i - 1]) > hi - lo) ys[i] = NaN; // poles
      layout.xaxis = axis2d(th, label(a), { range: R[a] });
      layout.yaxis = axis2d(th, label(spec.dep || "y"), { range: [lo, hi] });
      return { data: [{ type: "scatter", mode: "lines", x: xs, y: ys, line: { color: th.series, width: 2.5 } }], layout };
    }
    case "implicit2d": {
      const xs = linspace(...R.x, 220);
      const ys = linspace(...R.y, 220);
      const z = ys.map((y) => xs.map((x) => f[0]({ ...params, x, y })));
      layout.xaxis = axis2d(th, label("x"), { range: R.x });
      layout.yaxis = axis2d(th, label("y"), { range: R.y, scaleanchor: "x" });
      return { data: [{ type: "contour", x: xs, y: ys, z, showscale: false, contours: { start: 0, end: 0, size: 1, coloring: "none" },
        line: { color: th.series, width: 2.5 }, hoverinfo: "skip" }], layout };
    }
    case "polar": {
      const ts = linspace(...R.theta, N2 * 2);
      const rs = ts.map((theta) => f[0]({ ...params, theta }));
      layout.xaxis = axis2d(th, label("x"));
      layout.yaxis = axis2d(th, label("y"), { scaleanchor: "x" });
      return { data: [{ type: "scatter", mode: "lines", x: rs.map((r, i) => r * Math.cos(ts[i])),
        y: rs.map((r, i) => r * Math.sin(ts[i])), line: { color: th.series, width: 2.5 } }], layout };
    }
    case "parametric2d": {
      const p = spec.axes[0];
      const ts = linspace(...R[p], N2 * 3);
      layout.xaxis = axis2d(th, label("x"));
      layout.yaxis = axis2d(th, label("y"), { scaleanchor: "x" });
      return { data: [{ type: "scatter", mode: "lines", x: ts.map((v) => f[0]({ ...params, [p]: v })),
        y: ts.map((v) => f[1]({ ...params, [p]: v })), line: { color: th.series, width: 2.5 } }], layout };
    }
    case "parametric3d": {
      const p = spec.axes[0];
      const ts = linspace(...R[p], N2 * 3);
      const pts = ts.map((v) => f.map((g) => g({ ...params, [p]: v })));
      layout.scene = scene(th, ["x", "y", "z"], "data");
      return { data: [{ type: "scatter3d", mode: "lines", x: pts.map((q) => q[0]), y: pts.map((q) => q[1]),
        z: pts.map((q) => q[2]), line: { color: th.series, width: 5 } }], layout };
    }
    case "explicit3d": {
      const [a, b] = spec.axes;
      const xs = linspace(...R[a], NS);
      const ys = linspace(...R[b], NS);
      const z = ys.map((y) => xs.map((x) => f[0]({ ...params, [a]: x, [b]: y })));
      const [lo, hi] = robustRange(z.flat());
      const zc = z.map((row) => row.map((v) => (v < lo || v > hi ? NaN : v)));
      layout.scene = scene(th, [a, b, spec.dep || "z"], "cube");
      layout.scene.zaxis.range = [lo, hi];
      return { data: [surface(th, { x: xs, y: ys, z: zc })], layout };
    }
    case "cylindrical": case "spherical": case "surface3d": {
      const [a, b] = spec.axes;
      const us = linspace(...R[a], spec.kind === "cylindrical" ? 50 : 70);
      const vs = linspace(...R[b], 90);
      const X = [], Y = [], Z = [];
      for (const v of vs) {
        const xr = [], yr = [], zr = [];
        for (const u of us) {
          const s = { ...params, [a]: u, [b]: v };
          let x, y, z;
          if (spec.kind === "cylindrical") { x = u * Math.cos(v); y = u * Math.sin(v); z = f[0](s); }
          else if (spec.kind === "spherical") {
            const r = f[0](s);
            x = r * Math.sin(u) * Math.cos(v); y = r * Math.sin(u) * Math.sin(v); z = r * Math.cos(u);
          } else { x = f[0](s); y = f[1](s); z = f[2](s); }
          xr.push(x); yr.push(y); zr.push(z);
        }
        X.push(xr); Y.push(yr); Z.push(zr);
      }
      layout.scene = scene(th, ["x", "y", spec.kind === "cylindrical" ? spec.dep || "z" : "z"],
        spec.kind === "cylindrical" ? "cube" : "data");
      return { data: [surface(th, { x: X, y: Y, z: Z })], layout };
    }
    case "implicit3d": {
      const xs = linspace(...R.x, NI), ys = linspace(...R.y, NI), zs = linspace(...R.z, NI);
      const X = [], Y = [], Z = [], V = [];
      for (const x of xs) for (const y of ys) for (const z of zs) {
        X.push(x); Y.push(y); Z.push(z); V.push(f[0]({ ...params, x, y, z }));
      }
      const finite = V.filter(Number.isFinite);
      if (!finite.length || Math.min(...finite) > 0 || Math.max(...finite) < 0) throw new Error("the surface does not cross this range");
      layout.scene = scene(th, ["x", "y", "z"], "data");
      return { data: [{ type: "isosurface", x: X, y: Y, z: Z, value: V.map((v) => (Number.isFinite(v) ? v : 1e9)),
        isomin: 0, isomax: 0, surface: { count: 1 }, caps: { x: { show: false }, y: { show: false }, z: { show: false } },
        colorscale: [[0, th.series], [1, th.series]], showscale: false, flatshading: false,
        lighting: { ambient: 0.55, diffuse: 0.8, specular: 0.25, roughness: 0.6 } }], layout };
    }
    case "anim1d": {
      const a = spec.axes[0];
      const tname = spec.time;
      const { xs, ts, Z, lo, hi } = cached(key, () => {
        const xs = linspace(...R[a], 400);
        const ts = linspace(...R[tname], NH);
        const Z = ts.map((t) => xs.map((x) => f[0]({ ...params, [a]: x, [tname]: t })));
        const [lo, hi] = robustRange(Z.flat());
        return { xs, ts, Z, lo, hi };
      });
      const ys = xs.map((x) => f[0]({ ...params, [a]: x, [tname]: time }));
      const signed = lo < 0 && hi > 0;
      const m = Math.max(Math.abs(lo), Math.abs(hi));
      layout.grid = { rows: 1, columns: 2, pattern: "independent" };
      layout.xaxis = axis2d(th, label(a), { domain: [0, 0.6], range: R[a] });
      layout.yaxis = axis2d(th, label(spec.dep || "u"), { range: [lo, hi] });
      layout.xaxis2 = axis2d(th, label(a), { domain: [0.68, 1], range: R[a] });
      layout.yaxis2 = axis2d(th, label(tname), { range: R[tname] });
      layout.shapes = [{ type: "line", xref: "x2", yref: "y2", x0: R[a][0], x1: R[a][1], y0: time, y1: time,
        line: { color: th.text, width: 1.5 } }];
      return { data: [
        { type: "scatter", mode: "lines", x: xs, y: ys, line: { color: th.series, width: 2.5 } },
        { type: "heatmap", x: xs, y: ts, z: Z, xaxis: "x2", yaxis: "y2", colorscale: signed ? th.div : th.seq,
          zmin: signed ? -m : lo, zmax: signed ? m : hi, showscale: false, hoverinfo: "skip" },
      ], layout };
    }
    case "anim2d": {
      const tname = spec.time;
      const xs = linspace(...R.x, NH), ys = linspace(...R.y, NH);
      const field = (t) => ys.map((y) => xs.map((x) => f[0]({ ...params, x, y, [tname]: t })));
      const { lo, hi } = cached(key, () => {
        const samples = linspace(...R[tname], 6).flatMap((t) => field(t).flat().filter((_, i) => i % 7 === 0));
        const [lo, hi] = robustRange(samples);
        return { lo, hi };
      });
      const signed = lo < 0 && hi > 0;
      const m = Math.max(Math.abs(lo), Math.abs(hi));
      layout.xaxis = axis2d(th, label("x"), { range: R.x });
      layout.yaxis = axis2d(th, label("y"), { range: R.y, scaleanchor: "x" });
      return { data: [{ type: "heatmap", x: xs, y: ys, z: field(time), colorscale: signed ? th.div : th.seq,
        zmin: signed ? -m : lo, zmax: signed ? m : hi, colorbar: { tickfont: { color: th.text2 }, outlinewidth: 0 } }], layout };
    }
    default:
      throw new Error(`unknown plot type ${spec.kind}`);
  }
}

function scene(th, names, aspectmode) {
  return { xaxis: axis3d(th, names[0]), yaxis: axis3d(th, names[1]), zaxis: axis3d(th, names[2]), aspectmode,
    camera: { eye: { x: 1.5, y: 1.5, z: 1.1 } } };
}

function surface(th, xyz) {
  return { type: "surface", ...xyz, colorscale: th.seq, showscale: false,
    lighting: { ambient: 0.6, diffuse: 0.7, specular: 0.2, roughness: 0.7 }, contours: { z: { show: false } } };
}
