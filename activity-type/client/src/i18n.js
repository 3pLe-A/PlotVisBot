export const STRINGS = {
  en: {
    title: "PlotBot",
    placeholder: "A formula (LaTeX or plain) or a description, e.g. x(t) = A e^{-\\lambda_1 t} + B e^{-\\lambda_2 t}",
    plot: "Plot",
    working: "Working…",
    examples: "Examples",
    parameters: "Parameters",
    time: "Time",
    play: "Play",
    pause: "Pause",
    speed: "Speed",
    ranges: "Ranges",
    from: "from",
    to: "to",
    min: "min",
    max: "max",
    reset: "Reset",
    save: "Save",
    saved: "Saved as #{id}. Type #{id} in the box to reopen it.",
    loaded: "Loaded #{id}.",
    notFound: "No saved plot #{id} (it may have expired).",
    rewritten: "Rewritten as math",
    nlDisabled: "Natural-language prompts need an Anthropic API key on the server. Typed math works, e.g. y = sin(k x).",
    parseError: "I couldn't read this as math: {error}",
    nlError: "I couldn't turn this into a formula: {error}",
    renderError: "I couldn't draw this: {error}",
    empty: "Type a formula or a description, then press Plot.",
    hint: "Drag to rotate 3D plots, scroll to zoom. Sliders update the plot live.",
  },
  ru: {
    title: "PlotBot",
    placeholder: "Формула (LaTeX или обычная) или описание, напр. x(t) = A e^{-\\lambda_1 t} + B e^{-\\lambda_2 t}",
    plot: "Построить",
    working: "Строю…",
    examples: "Примеры",
    parameters: "Параметры",
    time: "Время",
    play: "Пуск",
    pause: "Пауза",
    speed: "Скорость",
    ranges: "Диапазоны",
    from: "от",
    to: "до",
    min: "мин",
    max: "макс",
    reset: "Сбросить",
    save: "Сохранить",
    saved: "Сохранено как #{id}. Введите #{id} в поле, чтобы открыть снова.",
    loaded: "Открыт график #{id}.",
    notFound: "График #{id} не найден (возможно, истёк срок хранения).",
    rewritten: "Запись в виде формулы",
    nlDisabled: "Для запросов на естественном языке на сервере нужен ключ Anthropic API. Формулы работают и так, напр. y = sin(k x).",
    parseError: "Не удалось прочитать формулу: {error}",
    nlError: "Не удалось превратить запрос в формулу: {error}",
    renderError: "Не удалось построить график: {error}",
    empty: "Введите формулу или описание и нажмите «Построить».",
    hint: "3D-графики можно вращать мышью и масштабировать колёсиком. Ползунки меняют график сразу.",
  },
};

export const EXAMPLES = [
  "x(t) = A e^{-\\lambda_1 t} + B e^{-\\lambda_2 t}, A=2, B=-1, \\lambda_2=3, t in [0, 6]",
  "x^2 + y^2 + z^2 = R^2, R=5",
  "u(x,t) = A sin(k x - omega t), k=1, omega=2",
  "r = 1 + a sin(3 theta) sin(4 phi), a=0.3",
  "z = sin(a x) cos(b y)",
  "u = exp(-(x^2+y^2)/(1+D t)) cos(omega t)",
  "((R + cos v) cos u, (R + cos v) sin u, sin v), R=2, v in [0, 2 pi]",
  "r = 1 + a sin(t) sin(3 theta) sin(4 phi), a=0.3",
  "morph(r = 2, (sqrt(x^2+y^2) - 2)^2 + z^2 = 0.5)",
  "затухающий осциллятор с частотой 3",
];

export function detect(text) {
  return /[А-Яа-яЁё]/.test(text || "") ? "ru" : null;
}

export function tr(lang, key, vars = {}) {
  const s = (STRINGS[lang] ?? STRINGS.en)[key] ?? STRINGS.en[key];
  return s.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ""));
}
