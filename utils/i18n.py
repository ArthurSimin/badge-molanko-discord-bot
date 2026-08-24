"""Simple i18n helper: load JSON locale files and resolve strings by Discord locale.

Locale files use Minecraft-style flat dotted keys, e.g.::

    {
        "version.command_description": "Show the bot version",
        "version.response": "Current version: **{version}**"
    }

Also provides MolankoTranslator for discord.app_commands command name/description
localization at sync time.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import discord
from discord import app_commands

from utils.user_locale import get_user_locale

logger = logging.getLogger("molanko.i18n")

LOCALES_DIR = Path(__file__).resolve().parents[1] / "locales"
DEFAULT_LOCALE = "en"

# Human-readable labels for supported locale codes (fallback if not in JSON)
LOCALE_DISPLAY_NAMES: dict[str, str] = {
    "auto": "Auto",
    "en": "English",
    "zh-CN": "Simplified Chinese",
}

# Cache loaded locale data: locale_code -> dict
_cache: dict[str, dict[str, Any]] = {}


def list_supported_locales() -> list[str]:
    """Return locale codes that have a JSON file under locales/ (sorted)."""
    if not LOCALES_DIR.is_dir():
        return [DEFAULT_LOCALE]
    codes = sorted(
        p.stem for p in LOCALES_DIR.glob("*.json") if p.is_file()
    )
    return codes or [DEFAULT_LOCALE]


def locale_display_name(code: str, for_locale: str | None = None) -> str:
    """Localized display name for a locale code (or Auto)."""
    if code == "auto":
        return t("language.choice.auto", locale=for_locale)
    # Prefer language.locale.<code> in translation files
    key = f"language.locale.{code}"
    name = t(key, locale=for_locale)
    if name != key:
        return name
    return LOCALE_DISPLAY_NAMES.get(code, code)


def _normalize_locale(locale: str | None) -> str:
    """Map Discord locale (e.g. zh-CN, en-US) to our file names."""
    if not locale:
        return DEFAULT_LOCALE
    loc = str(locale).replace("_", "-")
    if (LOCALES_DIR / f"{loc}.json").is_file():
        return loc
    lang = loc.split("-")[0].lower()
    if (LOCALES_DIR / f"{lang}.json").is_file():
        return lang
    if lang == "zh":
        if (LOCALES_DIR / "zh-CN.json").is_file():
            return "zh-CN"
        if (LOCALES_DIR / "zh.json").is_file():
            return "zh"
    return DEFAULT_LOCALE


def locale_for(interaction: discord.Interaction) -> str | None:
    """
    Effective locale for bot replies.

    Uses the user's saved preference when set; otherwise Discord client locale (Auto).
    """
    pref = get_user_locale(interaction.user.id)
    if pref and pref != "auto":
        return pref
    return str(interaction.locale) if interaction.locale else None


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


def _lookup(data: dict[str, Any], key: str) -> str | None:
    """Resolve a key. Prefer flat dotted keys (Minecraft-style), then nested."""
    if key in data and not isinstance(data[key], dict):
        return str(data[key])

    value: Any = data
    for part in key.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return None
    if value is None or isinstance(value, dict):
        return None
    return str(value)


def t(key: str, locale: str | None = None, **kwargs: Any) -> str:
    """
    Translate a key for the given locale.

    key format: dotted string e.g. "version.response" (Minecraft-style).
    Falls back to DEFAULT_LOCALE, then to the key itself.
    Supports simple str.format(**kwargs).
    """
    code = _normalize_locale(locale)
    value = _lookup(_load_locale(code), key)

    if value is None and code != DEFAULT_LOCALE:
        value = _lookup(_load_locale(DEFAULT_LOCALE), key)

    if value is None:
        return key

    text = value
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            logger.warning("Format failed for key=%s kwargs=%s", key, kwargs)
    return text


def clear_cache() -> None:
    """Clear loaded locale cache (useful after editing locale files)."""
    _cache.clear()


class MolankoTranslator(app_commands.Translator):
    """
    Translate app_commands locale_str using locales/*.json.

    Prefer extras["i18n_key"] when present (e.g. "version.command_description").
    Otherwise fall back to matching the English message string against en.json
    values (less reliable).

    Returns None when no translation is found so Discord keeps the default.
    """

    async def translate(
        self,
        string: app_commands.locale_str,
        locale: discord.Locale,
        context: app_commands.TranslationContext,
    ) -> str | None:
        code = _normalize_locale(locale.value if locale else None)
        if code == DEFAULT_LOCALE:
            return None

        key = string.extras.get("i18n_key") if string.extras else None
        if key:
            value = _lookup(_load_locale(code), key)
            if value is not None:
                return value
            return None

        message = str(string)
        en_data = _load_locale(DEFAULT_LOCALE)
        found_key = _find_key_by_value(en_data, message)
        if found_key:
            value = _lookup(_load_locale(code), found_key)
            if value is not None:
                return value

        return None


def _find_key_by_value(data: dict[str, Any], target: str, prefix: str = "") -> str | None:
    """Find a key whose string value equals target (supports flat and nested)."""
    for k, v in data.items():
        path = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            found = _find_key_by_value(v, target, path)
            if found:
                return found
        elif isinstance(v, str) and v == target:
            return k if not prefix else path
    return None
