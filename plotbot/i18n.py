"""User-facing strings in English and Russian."""

from __future__ import annotations

import re

STRINGS = {
    "en": {
        "rewritten": "Rewritten as math",
        "parameters": "Parameters",
        "selected": "Selected",
        "set_values": "Set values…",
        "reset": "Reset",
        "form_title": "Plot parameters",
        "range_label": "Range of {axis} (e.g. -5..5)",
        "pick_param": "Parameter to change",
        "parse_error": "I couldn't read this as math: {error}",
        "nl_error": "I couldn't turn this into a formula: {error}",
        "nl_disabled": "Natural-language prompts need an Anthropic API key on the bot's server. Plain math works, e.g. `y = sin(k x)`.",
        "render_error": "I couldn't draw this: {error}",
        "timeout": "Drawing took too long. Try a simpler formula or a smaller range.",
        "expired": "This plot has expired. Run /plot again.",
        "not_owner": "Only the person who created this plot can change it.",
        "bad_value": "Not a valid number: {value}",
        "lang_set": "Language set to English.",
        "tex_error": "LaTeX error: {error}",
        "animated": "Animated over {time}",
        "help": (
            "**/plot** `prompt` draws any formula or description, for example:\n"
            "• `x^2 + y^2 + z^2 = 25` (implicit 3D surface)\n"
            "• `x(t) = A e^{-\\lambda_1 t} + B e^{-\\lambda_2 t}` (buttons change A, B, λ)\n"
            "• `u(x,t) = sin(x - c t)` (1D + time, animated)\n"
            "• `r = 1 + cos(theta)` (polar), `(cos t, sin t, t/5)` (parametric)\n"
            "• `a damped oscillator with frequency 3` (natural language)\n"
            "Add `, A=2` to set a parameter and `, x in [0, 10]` to set a range.\n"
            "**/tex** `source` renders LaTeX text and math. **/language** switches ru/en."
        ),
    },
    "ru": {
        "rewritten": "Запись в виде формулы",
        "parameters": "Параметры",
        "selected": "Выбран",
        "set_values": "Задать значения…",
        "reset": "Сбросить",
        "form_title": "Параметры графика",
        "range_label": "Диапазон {axis} (напр. -5..5)",
        "pick_param": "Какой параметр менять",
        "parse_error": "Не удалось прочитать формулу: {error}",
        "nl_error": "Не удалось превратить запрос в формулу: {error}",
        "nl_disabled": "Для запросов на естественном языке на сервере бота нужен ключ Anthropic API. Формулы работают и без него, например `y = sin(k x)`.",
        "render_error": "Не удалось построить график: {error}",
        "timeout": "Построение заняло слишком много времени. Упростите формулу или уменьшите диапазон.",
        "expired": "Срок хранения графика истёк. Запустите /plot снова.",
        "not_owner": "Изменять график может только его автор.",
        "bad_value": "Некорректное число: {value}",
        "lang_set": "Язык переключён на русский.",
        "tex_error": "Ошибка LaTeX: {error}",
        "animated": "Анимация по {time}",
        "help": (
            "**/plot** `запрос` строит график формулы или описания, например:\n"
            "• `x^2 + y^2 + z^2 = 25` (неявная поверхность в 3D)\n"
            "• `x(t) = A e^{-\\lambda_1 t} + B e^{-\\lambda_2 t}` (кнопки меняют A, B, λ)\n"
            "• `u(x,t) = sin(x - c t)` (1D + время, анимация)\n"
            "• `r = 1 + cos(theta)` (полярные), `(cos t, sin t, t/5)` (параметрическая)\n"
            "• `затухающий осциллятор с частотой 3` (обычный текст)\n"
            "Добавьте `, A=2`, чтобы задать параметр, и `, x in [0, 10]` для диапазона.\n"
            "**/tex** `текст` отображает LaTeX (текст и формулы). **/language** переключает ru/en."
        ),
    },
}

_CYRILLIC = re.compile(r"[А-Яа-яЁё]")


def detect(text: str, locale: str | None = None) -> str:
    if _CYRILLIC.search(text or ""):
        return "ru"
    if locale and str(locale).lower().startswith("ru"):
        return "ru"
    return "en"


def t(lang: str, key: str, **kwargs: object) -> str:
    table = STRINGS.get(lang, STRINGS["en"])
    return table.get(key, STRINGS["en"][key]).format(**kwargs)
