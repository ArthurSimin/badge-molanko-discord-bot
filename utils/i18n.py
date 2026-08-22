"""Simple i18n helper: load JSON locale files and resolve strings by Discord locale."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("molanko.i18n")

LOCALES_DIR = Path(__file__).resolve().parents[1] / "locales"
DEFAULT_LOCALE = "en"

# Cache loaded locale data: locale_code -> dict
_cache: dict[str, dict[str, Any]] = {}


def _normalize_locale(locale: str | None) -> str:
    """Map Discord locale (e.g. zh-CN, en-US) to our file names."""
    if not locale:
        return DEFAULT_LOCALE
    loc = str(locale).replace("_", "-")
    # Exact match first
    if (LOCALES_DIR / f"{loc}.json").is_file():
        return loc
    # Language-only fallback (zh-CN -> zh, en-US -> en)
    lang = loc.split("-")[0].lower()
    if (LOCALES_DIR / f"{lang}.json").is_file():
        return lang
    # Common aliases
    if lang == "zh":
        # Prefer Simplified Chinese file if present
        if (LOCALES_DIR / "zh-CN.json").is_file():
            return "zh-CN"
        if (LOCALES_DIR / "zh.json").is_file():
            return "zh"
    return DEFAULT_LOCALE


def _load_locale(code: str) -> dict[str, Any]:
    if code in _cache:
        return _cache[code]
    path = LOCALES_DIR / f"{code}.json"
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to load locale file %s", path)
    else:
        logger.warning("Locale file not found: %s", path)
    _cache[code] = data
    return data


def t(key: str, locale: str | None = None, **kwargs: Any) -> str:
    """
    Translate a key for the given locale.

    key format: "cog.section.key" e.g. "version.response"
    Falls back to DEFAULT_LOCALE, then to the key itself.
    Supports simple str.format(**kwargs).
    """
    code = _normalize_locale(locale)
    data = _load_locale(code)

    # Nested lookup by dots
    value: Any = data
    for part in key.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            value = None
            break

    if value is None and code != DEFAULT_LOCALE:
        # Fallback to default locale
        data = _load_locale(DEFAULT_LOCALE)
        value = data
        for part in key.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                value = None
                break

    if value is None:
        return key

    text = str(value)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            logger.warning("Format failed for key=%s kwargs=%s", key, kwargs)
    return text


def clear_cache() -> None:
    """Clear loaded locale cache (useful after editing locale files)."""
    _cache.clear()
