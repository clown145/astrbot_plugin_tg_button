"""Utility helpers for Telegram parse mode handling and metadata generation."""
from __future__ import annotations

from typing import Any, Dict, Optional

# Canonical enum values that are exposed to the WebUI/metadata layer.
PARSE_MODE_ENUM = ("html", "markdown", "markdownv2", "none")

# Human readable labels for the dropdown list.
PARSE_MODE_LABELS: Dict[str, str] = {
    "html": "HTML",
    "markdown": "Markdown",
    "markdownv2": "Markdown V2",
    "none": "纯文本",
}

# Mapping from canonical enum value to Telegram Bot API parse mode string.
_PARSE_MODE_TO_TELEGRAM: Dict[str, Optional[str]] = {
    "html": "HTML",
    "markdown": "Markdown",
    "markdownv2": "MarkdownV2",
    "none": None,
}

# Aliases that should resolve to the same canonical enum value.
_ALIAS_TO_CANONICAL: Dict[str, str] = {
    "html": "html",
    "": "html",
    "plain": "none",
    "none": "none",
    "markdown": "markdown",
    "md": "markdown",
    "markdownv2": "markdownv2",
    "mdv2": "markdownv2",
}


def canonical_parse_mode_alias(value: Optional[str], *, default: str = "html") -> str:
    """Return the canonical enum value for the provided parse mode alias."""
    candidate = str(value or "").strip().lower()
    if candidate in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[candidate]
    # Fallback to default when the value is not recognised.
    if default not in PARSE_MODE_ENUM:
        default = "html"
    return default


def map_to_telegram_parse_mode(value: Optional[str], *, default: str = "html") -> Optional[str]:
    """Resolve an alias to the Telegram parse mode string accepted by the API."""
    alias = canonical_parse_mode_alias(value, default=default)
    return _PARSE_MODE_TO_TELEGRAM.get(alias)


def build_parse_mode_input(*, description: str, default: str = "html", required: bool = False) -> Dict[str, Any]:
    """Return a metadata entry describing a parse mode dropdown input."""
    alias_default = canonical_parse_mode_alias(default)
    return {
        "name": "parse_mode",
        "type": "string",
        "required": required,
        "default": alias_default,
        "description": description,
        "enum": list(PARSE_MODE_ENUM),
        "enum_labels": dict(PARSE_MODE_LABELS),
    }
