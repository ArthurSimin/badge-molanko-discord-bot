"""Per-user language preference persistence."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

logger = logging.getLogger("molanko.user_locale")

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
STORE_PATH = DATA_DIR / "user_locales.json"

# user_id (str) -> locale code ("auto" is not stored; missing key means auto)
_prefs: dict[str, str] = {}
_loaded = False
_lock = threading.Lock()


def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        if STORE_PATH.is_file():
            try:
                raw = json.loads(STORE_PATH.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    for k, v in raw.items():
                        if isinstance(k, str) and isinstance(v, str) and v and v != "auto":
                            _prefs[k] = v
            except Exception:
                logger.exception("Failed to load user locale store %s", STORE_PATH)
        _loaded = True


def _save() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STORE_PATH.with_suffix(".json.tmp")
    try:
        tmp.write_text(
            json.dumps(_prefs, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp.replace(STORE_PATH)
    except Exception:
        logger.exception("Failed to save user locale store %s", STORE_PATH)
        try:
            if tmp.is_file():
                tmp.unlink()
        except Exception:
            pass


def get_user_locale(user_id: int) -> str:
    """Return stored locale code, or 'auto' if unset."""
    _ensure_loaded()
    return _prefs.get(str(user_id), "auto")


def set_user_locale(user_id: int, locale: str) -> None:
    """
    Persist user locale preference.

    locale 'auto' removes the override (follow Discord client language).
    """
    _ensure_loaded()
    key = str(user_id)
    with _lock:
        if not locale or locale == "auto":
            _prefs.pop(key, None)
        else:
            _prefs[key] = locale
        _save()
