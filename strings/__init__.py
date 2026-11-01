# Copyright (C) 2024 by Badhacker98@Github
# Owner https://t.me/ll_BAD_MUNDA_ll

"""
strings/__init__.py
Loads en.yml (or any language yml) and provides get_string(lang).
Usage:
    from strings import get_string
    _ = get_string("en")
    text = _["start_group"]
"""

import os
import logging

try:
    import yaml
    _YAML_OK = True
except ImportError:
    _YAML_OK = False

logger = logging.getLogger("Strings")

_cache: dict = {}

_STRINGS_DIR = os.path.dirname(__file__)


def _load(lang: str) -> dict:
    if lang in _cache:
        return _cache[lang]

    path = os.path.join(_STRINGS_DIR, f"{lang}.yml")
    if not os.path.exists(path):
        path = os.path.join(_STRINGS_DIR, "en.yml")

    if not _YAML_OK:
        logger.warning("PyYAML not installed — strings unavailable. Run: pip install pyyaml")
        return {}

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        _cache[lang] = data
        return data
    except Exception as e:
        logger.error(f"strings: failed to load {path}: {e}")
        return {}


def get_string(lang: str = "en") -> dict:
    """Return the string dict for the given language code (default: 'en')."""
    return _load(lang)
