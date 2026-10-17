import Plotly from "plotly.js-dist-min";
import katex from "katex";
import "katex/dist/katex.min.css";
import "./style.css";

import { buildFigure } from "./figure.js";
import { EXAMPLES, detect, tr } from "./i18n.js";
import { MathParseError, looksLikeMath, number, parseMath, pretty, symbolTex } from "./mathparse.js";
import { connectDiscord, insideDiscord } from "./discord.js";

const $ = (id) => document.getElementById(id);
const els = {
  form: $("prompt-form"), prompt: $("prompt"), go: $("go"), examples: $("examples"), formula: $("formula"),
  explanation: $("explanation"), message: $("message"), plot: $("plot"), controls: $("controls"),
  params: $("params"), paramsBox: $("params-box"), timeBox: $("time-box"), play: $("play"), time: $("time"),
  timeValue: $("time-value"), speed: $("speed"), ranges: $("ranges"), reset: $("reset"), save: $("save"),
};

const state = {
  lang: loadLang(),
  spec: null,
  params: {},
  initial: {},
  bounds: {},
  time: 0,
  playing: false,
  prompt: "",
  explanation: "",
  math: "",
  naturalLanguage: false,
  discord: null,
};

// --------------------------------------------------------------------------- language

function loadLang() {
  try {
    const saved = localStorage.getItem("plotbot.lang");
    if (saved === "en" || saved === "ru") return saved;
  } catch { /* storage unavailable */ }
  return navigator.language?.toLowerCase().startsWith("ru") ? "ru" : "en";
}

function setLang(lang) {
  state.lang = lang;
  try { localStorage.setItem("plotbot.lang", lang); } catch { /* storage unavailable */ }
  document.documentElement.lang = lang;
  for (const el of document.querySelectorAll("[data-i18n]")) el.textContent = tr(lang, el.dataset.i18n);
  for (const b of document.querySelectorAll("[data-lang]")) b.setAttribute("aria-pressed", String(b.dataset.lang === lang));
  els.prompt.placeholder = tr(lang, "placeholder");
  els.play.textContent = tr(lang, state.playing ? "pause" : "play");
  if (state.spec) renderControls();
}

function say(key, vars, isError = false) {
  els.message.textContent = key ? tr(state.lang, key, vars) : "";
  els.message.classList.toggle("error", isError);
}

// --------------------------------------------------------------------------- pipeline

async function api(path, body) {
  const headers = { "Content-Type": "application/json" };
  if (state.discord?.accessToken) headers.Authorization = `Bearer ${state.discord.accessToken}`;
  const res = await fetch(path, body ? { method: "POST", headers, body: JSON.stringify(body) } : { headers });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json.error || res.statusText);
  return json;
}

async function makeSpec(prompt) {
  if (looksLikeMath(prompt) || !state.naturalLanguage) {
    try {
      return { spec: parseMath(prompt), explanation: "", math: prompt };
    } catch (e) {
      if (!state.naturalLanguage) throw e;
    }
  }
  let result;
  try {
    result = await api("/api/translate", { prompt });
  } catch (e) {
    throw Object.assign(new Error(e.message), { nl: true });
  }
  if (!result.ok) throw Object.assign(new Error(result.explanation), { nl: true });
  const spec = parseMath(result.math);
  spec.source = prompt;
  return { spec, explanation: result.explanation, math: result.math };
}

async function plotPrompt(prompt, saved = null) {
  prompt = prompt.trim();
  if (!prompt) return say("empty");
  const savedId = /^#([0-9a-f]{12})$/i.exec(prompt)?.[1];
  if (savedId && !saved) return loadSaved(savedId);
  const lang = detect(prompt);
  if (lang && lang !== state.lang) setLang(lang);
  els.go.disabled = true;
  els.go.textContent = tr(state.lang, "working");
  say("");
  try {
    const { spec, explanation, math } = saved
      ? { spec: parseMath(saved.math), explanation: saved.explanation, math: saved.math }
      : await makeSpec(prompt);
    spec.source = prompt;
    state.spec = spec;
    state.math = math;
    state.prompt = prompt;
    state.explanation = explanation;
    state.initial = { ...spec.params };
    state.params = { ...(saved?.params ?? spec.params) };
    if (saved?.ranges) Object.assign(spec.ranges, saved.ranges);
    state.bounds = Object.fromEntries(Object.entries(state.params).map(([k, v]) => [k, defaultBounds(v)]));
    state.time = spec.time ? spec.ranges[spec.time][0] : 0;
    setPlaying(Boolean(spec.time));
    els.prompt.value = prompt;
    showFormula();
    renderControls();
    draw();
  } catch (e) {
    if (e instanceof MathParseError) say(state.naturalLanguage ? "parseError" : "nlDisabled", { error: e.message }, true);
    else if (e.nl) say("nlError", { error: e.message }, true);
    else say("renderError", { error: e.message }, true);
  } finally {
    els.go.disabled = false;
    els.go.textContent = tr(state.lang, "plot");
  }
}

function defaultBounds(v) {
  const span = Math.max(Math.abs(v) * 2, 2);
  return [round(v - span), round(v + span)];
}

const round = (v) => Number(v.toPrecision(6));

function showFormula() {
  katex.render(state.spec.latex, els.formula, { displayMode: true, throwOnError: false });
  els.explanation.textContent = state.explanation ? `${tr(state.lang, "rewritten")}: ${state.explanation}` : "";
}

// --------------------------------------------------------------------------- drawing

let frame = 0;
function draw() {
  if (frame) return;
  frame = requestAnimationFrame(() => {
    frame = 0;
    if (!state.spec) return;
    try {
      const { data, layout } = buildFigure(state.spec, state.params, state.time);
      Plotly.react(els.plot, data, layout, {
        responsive: true, displaylogo: false, modeBarButtonsToRemove: ["toImage", "sendDataToCloud"],
      });
      if (els.message.classList.contains("error")) say("");
    } catch (e) {
      say("renderError", { error: e.message }, true);
    }
  });
}

// --------------------------------------------------------------------------- controls

function renderControls() {
  const { spec } = state;
  els.controls.hidden = false;
  els.params.replaceChildren();
  const names = Object.keys(state.params).sort();
  els.paramsBox.hidden = names.length === 0;
  for (const name of names) els.params.append(paramRow(name));

  els.timeBox.hidden = !spec.time;
  if (spec.time) syncTimeSlider();

  els.ranges.replaceChildren();
  for (const axis of [...spec.axes, ...(spec.time ? [spec.time] : [])]) els.ranges.append(rangeRow(axis));
}

function paramRow(name) {
  const row = document.createElement("div");
  row.className = "param";
  const [lo, hi] = state.bounds[name];
  row.innerHTML = `
    <div class="param-head"><span class="sym"></span><input type="number" step="any" aria-label="${pretty(name)}"></div>
    <input type="range" min="${lo}" max="${hi}" step="${(hi - lo) / 400}" aria-label="${pretty(name)}">
    <div class="bounds">
      <label>${tr(state.lang, "min")} <input type="number" step="any" value="${lo}" data-b="0"></label>
      <label>${tr(state.lang, "max")} <input type="number" step="any" value="${hi}" data-b="1"></label>
    </div>`;
  katex.render(symbolTex(name), row.querySelector(".sym"), { throwOnError: false });
  const value = row.querySelector(".param-head input");
  const slider = row.querySelector('input[type="range"]');
  value.value = state.params[name];
  slider.value = state.params[name];
  slider.addEventListener("input", () => {
    state.params[name] = Number(slider.value);
    value.value = round(state.params[name]);
    draw();
  });
  value.addEventListener("change", () => {
    const v = Number(value.value);
    if (!Number.isFinite(v)) return;
    state.params[name] = v;
    const [a, b] = state.bounds[name];
    if (v < a || v > b) { state.bounds[name] = defaultBounds(v); renderControls(); }
    else slider.value = v;
    draw();
  });
  for (const input of row.querySelectorAll("[data-b]")) {
    input.addEventListener("change", () => {
      const v = Number(input.value);
      const b = [...state.bounds[name]];
      b[input.dataset.b] = v;
      if (Number.isFinite(v) && b[0] < b[1]) { state.bounds[name] = b; renderControls(); }
    });
  }
  return row;
}

function rangeRow(axis) {
  const row = document.createElement("div");
  row.className = "range-row";
  const [a, b] = state.spec.ranges[axis];
  row.innerHTML = `<span>${pretty(axis)}</span>
    <input type="text" value="${round(a)}" aria-label="${pretty(axis)} ${tr(state.lang, "from")}">
    <input type="text" value="${round(b)}" aria-label="${pretty(axis)} ${tr(state.lang, "to")}">`;
  const [lo, hi] = row.querySelectorAll("input");
  const apply = () => {
    try {
      const r = [number(lo.value), number(hi.value)];
      if (r[0] >= r[1]) throw new Error();
      state.spec.ranges[axis] = r;
      if (axis === state.spec.time) { state.time = Math.min(Math.max(state.time, r[0]), r[1]); syncTimeSlider(); }
      lo.style.borderColor = hi.style.borderColor = "";
      draw();
    } catch {
      lo.style.borderColor = hi.style.borderColor = "var(--danger)";
    }
  };
  lo.addEventListener("change", apply);
  hi.addEventListener("change", apply);
  return row;
}

// --------------------------------------------------------------------------- time

function syncTimeSlider() {
  const [a, b] = state.spec.ranges[state.spec.time];
  els.time.value = String(Math.round(((state.time - a) / (b - a)) * 1000));
  els.timeValue.value = `${pretty(state.spec.time)} = ${state.time.toFixed(2)}`;
}

function setPlaying(on) {
  state.playing = on;
  els.play.textContent = tr(state.lang, on ? "pause" : "play");
  if (on) requestAnimationFrame(tick);
}

let last = 0;
function tick(now) {
  if (!state.playing || !state.spec?.time) { last = 0; return; }
  const dt = last ? Math.min((now - last) / 1000, 0.1) : 0;
  last = now;
  const [a, b] = state.spec.ranges[state.spec.time];
  // One sweep of the time range takes 8 s at speed 1.
  state.time += ((b - a) / 8) * Number(els.speed.value) * dt;
  if (state.time > b) state.time = a + ((state.time - a) % (b - a));
  syncTimeSlider();
  draw();
  requestAnimationFrame(tick);
}

els.play.addEventListener("click", () => setPlaying(!state.playing));
els.time.addEventListener("input", () => {
  const [a, b] = state.spec.ranges[state.spec.time];
  state.time = a + (Number(els.time.value) / 1000) * (b - a);
  setPlaying(false);
  syncTimeSlider();
  draw();
});

// --------------------------------------------------------------------------- save / load

els.save.addEventListener("click", async () => {
  if (!state.spec) return;
  try {
    const { id } = await api("/api/plots", {
      lang: state.lang, prompt: state.prompt, channelId: state.discord?.channelId,
      state: { math: state.math, explanation: state.explanation, params: state.params, ranges: state.spec.ranges },
    });
    say("saved", { id });
  } catch (e) {
    say("renderError", { error: e.message }, true);
  }
});

async function loadSaved(id) {
  try {
    const row = await api(`/api/plots/${id}`);
    setLang(row.lang);
    // The saved row holds the math text, so natural-language plots reopen without calling Claude again.
    await plotPrompt(row.prompt, row.state);
    say("loaded", { id });
  } catch {
    say("notFound", { id }, true);
  }
}

els.reset.addEventListener("click", () => {
  if (!state.spec) return;
  state.params = { ...state.initial };
  state.bounds = Object.fromEntries(Object.entries(state.params).map(([k, v]) => [k, defaultBounds(v)]));
  renderControls();
  draw();
});

// --------------------------------------------------------------------------- start

els.form.addEventListener("submit", (e) => { e.preventDefault(); plotPrompt(els.prompt.value); });
els.prompt.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); plotPrompt(els.prompt.value); }
});
for (const b of document.querySelectorAll("[data-lang]")) b.addEventListener("click", () => setLang(b.dataset.lang));
for (const ex of EXAMPLES) {
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = ex;
  b.addEventListener("click", () => { els.prompt.value = ex; plotPrompt(ex); });
  els.examples.append(b);
}
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", draw);

setLang(state.lang);

(async () => {
  try {
    state.naturalLanguage = (await api("/api/config")).naturalLanguage;
  } catch { /* server unreachable: typed math still works */ }
  let first = new URLSearchParams(location.search).get("plot");
  if (insideDiscord()) {
    try {
      state.discord = await connectDiscord();
      if (state.discord.prompt) {
        await plotPrompt(state.discord.prompt);
        return;
      }
    } catch (e) {
      console.warn("Discord SDK:", e);
    }
  }
  if (first && /^[0-9a-f]{12}$/i.test(first)) return loadSaved(first);
  first = EXAMPLES[0];
  els.prompt.value = first;
  plotPrompt(first);
})();
