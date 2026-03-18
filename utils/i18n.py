"""Multi-language support for the Pokemon Bot."""
import json
import os
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

SUPPORTED_LANGS = ["ko", "en", "zh-hans", "zh-hant"]
DEFAULT_LANG = "ko"
FALLBACK_LANG = "ko"

_strings: dict[str, dict] = {}  # {lang: {key: value}}
_user_lang_cache: dict[int, str] = {}  # {user_id: lang}

def load_locales():
    """Load all locale JSON files from locales/ directory."""
    global _strings
    locales_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "locales")
    for lang in SUPPORTED_LANGS:
        filepath = os.path.join(locales_dir, f"{lang}.json")
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                _strings[lang] = json.load(f)
            logger.info(f"Loaded locale: {lang} ({len(_strings[lang])} keys)")
        except FileNotFoundError:
            logger.warning(f"Locale file not found: {filepath}")
            _strings[lang] = {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in locale {lang}: {e}")
            _strings[lang] = {}

def _get_nested(d: dict, key: str):
    """Get nested dict value by dot-separated key. e.g. 'spawn.wild_appeared'"""
    parts = key.split(".")
    for part in parts:
        if isinstance(d, dict):
            d = d.get(part)
        else:
            return None
    return d

def t(lang: str, key: str, **kwargs) -> str:
    """Translate a key to the given language.

    Args:
        lang: Language code (ko, en, zh-hans, zh-hant)
        key: Dot-separated key (e.g. 'spawn.wild_appeared')
        **kwargs: Format variables (e.g. name="피카츄")

    Returns:
        Translated string, or fallback to Korean if not found.
    """
    if lang not in _strings:
        lang = FALLBACK_LANG

    result = _get_nested(_strings.get(lang, {}), key)

    # Fallback to Korean
    if result is None and lang != FALLBACK_LANG:
        result = _get_nested(_strings.get(FALLBACK_LANG, {}), key)

    # Still not found — return key itself
    if result is None:
        return key

    # Apply format variables
    if kwargs and isinstance(result, str):
        try:
            result = result.format(**kwargs)
        except (KeyError, IndexError):
            pass

    return result

def get_cached_lang(user_id: int) -> str:
    """Get user language from cache (fast path)."""
    return _user_lang_cache.get(user_id, DEFAULT_LANG)

def set_cached_lang(user_id: int, lang: str):
    """Set user language in cache."""
    if lang in SUPPORTED_LANGS:
        _user_lang_cache[user_id] = lang

async def get_user_lang(user_id: int) -> str:
    """Get user language from cache or DB."""
    if user_id in _user_lang_cache:
        return _user_lang_cache[user_id]

    # Load from DB
    try:
        from database.connection import get_db
        pool = await get_db()
        lang = await pool.fetchval(
            "SELECT language FROM users WHERE user_id = $1", user_id
        )
        if lang and lang in SUPPORTED_LANGS:
            _user_lang_cache[user_id] = lang
            return lang
    except Exception:
        pass

    return DEFAULT_LANG

async def set_user_lang(user_id: int, lang: str):
    """Set user language in DB and cache."""
    if lang not in SUPPORTED_LANGS:
        return

    _user_lang_cache[user_id] = lang
    try:
        from database.connection import get_db
        pool = await get_db()
        await pool.execute(
            "UPDATE users SET language = $1 WHERE user_id = $2", lang, user_id
        )
    except Exception as e:
        logger.error(f"Failed to set language for {user_id}: {e}")

async def get_group_lang(chat_id: int) -> str:
    """Get group/channel default language."""
    try:
        from database.connection import get_db
        pool = await get_db()
        lang = await pool.fetchval(
            "SELECT language FROM chat_rooms WHERE chat_id = $1", chat_id
        )
        if lang and lang in SUPPORTED_LANGS:
            return lang
    except Exception:
        pass
    return DEFAULT_LANG

async def set_group_lang(chat_id: int, lang: str):
    """Set group/channel default language."""
    if lang not in SUPPORTED_LANGS:
        return
    try:
        from database.connection import get_db
        pool = await get_db()
        await pool.execute(
            "UPDATE chat_rooms SET language = $1 WHERE chat_id = $2", lang, chat_id
        )
    except Exception as e:
        logger.error(f"Failed to set group language for {chat_id}: {e}")

def poke_name(pokemon: dict, lang: str) -> str:
    """Get pokemon name in the correct language."""
    if lang == "ko":
        return pokemon.get("name_ko", pokemon.get("name", "???"))
    elif lang == "en":
        return pokemon.get("name_en", pokemon.get("name_ko", "???"))
    elif lang in ("zh-hans", "zh-hant"):
        key = f"name_{lang.replace('-', '_')}"
        return pokemon.get(key, pokemon.get("name_en", pokemon.get("name_ko", "???")))
    return pokemon.get("name_ko", "???")

# Language display names
LANG_LABELS = {
    "ko": "\ud83c\uddf0\ud83c\uddf7 \ud55c\uad6d\uc5b4",
    "en": "\ud83c\uddfa\ud83c\uddf8 English",
    "zh-hans": "\ud83c\udde8\ud83c\uddf3 \u7b80\u4f53\u4e2d\u6587",
    "zh-hant": "\ud83c\uddf9\ud83c\uddfc \u7e41\u9ad4\u4e2d\u6587",
}

# Load locales on import
load_locales()
