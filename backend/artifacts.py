"""Генерация промокода и реферального кода (по ТЗ).

Уникальность по базе бота проверяется на интеграции (Этап 6); здесь — генерация формата.
"""
from __future__ import annotations

import random

# Без 0/O/I/1 — чтобы не путались
CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# Простая транслитерация кириллицы для реферального кода
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _tail(n: int = 4) -> str:
    return "".join(random.choice(CHARS) for _ in range(n))


def transliterate(name: str) -> str:
    out = []
    for ch in name.lower():
        out.append(_TRANSLIT.get(ch, ch if ch.isalnum() else ""))
    return "".join(out)


def generate_promo_code() -> str:
    """Промокод вида TURK-XXXX."""
    return f"TURK-{_tail(4)}"


def generate_referral_code(name: str) -> str:
    """Реферальный код вида <имя-латиницей>_XXXX."""
    slug = transliterate(name).strip() or "user"
    return f"{slug}_{_tail(4)}"
