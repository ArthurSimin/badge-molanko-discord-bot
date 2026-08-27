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
    "debug": "Debug",
    "unknown": "Unknown",
    "en": "English",
    "en-US": "English (United States)",
    "en-GB": "English (United Kingdom)",
    "zh": "中文",
    "zh-Hans": "中文 (简体)",
    "zh-Hant": "中文 (繁體)",
    "zh-CN": "中文 (中国)",
    "zh-TW": "中文 (台灣)",
    "zh-HK": "中文 (香港)",
    "zh-MO": "中文 (澳門)",
    "zh-SG": "中文 (新加坡)",
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
    """
    Normalize Discord locale to our locale naming convention.

    This function does not perform fallback. Fallback is handled by
    _locale_fallbacks().
    """
    if not locale:
        return DEFAULT_LOCALE

    return str(locale).replace("_", "-")


def _locale_fallbacks(locale: str | None) -> list[str]:
    """
    Return locale fallback chain from most specific to least specific.

    Examples:
        zh-CN -> zh-CN -> zh-Hans -> zh -> en
        zh-TW -> zh-TW -> zh-Hant -> zh -> en
        zh-HK -> zh-HK -> zh-Hant -> zh -> en
        zh-MO -> zh-MO -> zh-Hant -> zh -> en
        zh-SG -> zh-SG -> zh-Hans -> zh -> en
        en-US -> en-US -> en
        fr-CA -> fr-CA -> fr -> en
    """
    code = _normalize_locale(locale)

    fallbacks: list[str] = []

    def add(value: str) -> None:
        if value in fallbacks:
            return

        if (LOCALES_DIR / f"{value}.json").is_file():
            fallbacks.append(value)

    # Exact locale first.
    add(code)

    # Chinese regional/script fallbacks.
    if code == "zh-CN":
        add("zh-Hans")
        add("zh")

    elif code == "zh-SG":
        add("zh-Hans")
        add("zh")

    elif code in {"zh-TW", "zh-HK", "zh-MO"}:
        add("zh-Hant")
        add("zh")

    elif code == "zh-Hans":
        add("zh")

    elif code == "zh-Hant":
        add("zh")

    else:
        # Generic language fallback.
        #
        # For example:
        #   en-US -> en
        #   fr-CA -> fr
        #   de-DE -> de
        lang = code.split("-")[0].lower()

        if lang != code:
            add(lang)

    # English is always the final fallback.
    add(DEFAULT_LOCALE)

    # DEFAULT_LOCALE should normally exist, but keep the function
    # safe if the locale directory is missing or misconfigured.
    if not fallbacks:
        return [DEFAULT_LOCALE]

    return fallbacks


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

    Uses the following fallback order:

        zh-CN -> zh-Hans -> zh -> en -> key
        zh-TW -> zh-Hant -> zh -> en -> key
        zh-HK -> zh-Hant -> zh -> en -> key
        zh-MO -> zh-Hant -> zh -> en -> key
        zh-SG -> zh-Hans -> zh -> en -> key

    For other regional locales:

        xx-YY -> xx -> en -> key

    Supports simple str.format(**kwargs).
    """
    for code in _locale_fallbacks(locale):
        value = _lookup(_load_locale(code), key)

        if value is None:
            continue

        text = value

        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, ValueError):
                logger.warning(
                    "Format failed for key=%s kwargs=%s",
                    key,
                    kwargs,
                )

        return text

    return key


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
        code = locale.value if locale else None
        normalized = _normalize_locale(code)

        # English is Discord's default source string, so there is no need
        # to provide a translation for it.
        if normalized == DEFAULT_LOCALE:
            return None

        key = string.extras.get("i18n_key") if string.extras else None
        if key:
            # Do not return English here. Returning None allows Discord
            # to keep the original/default command text.
            for fallback in _locale_fallbacks(code):
                if fallback == DEFAULT_LOCALE:
                    break

                value = _lookup(_load_locale(fallback), key)

                if value is not None:
                    return value

            return None

        message = str(string)
        en_data = _load_locale(DEFAULT_LOCALE)
        found_key = _find_key_by_value(en_data, message)
        if found_key:
            for fallback in _locale_fallbacks(code):
                if fallback == DEFAULT_LOCALE:
                    break

                value = _lookup(_load_locale(fallback), found_key)

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
