"""Utility helpers for handling Telegram parse modes across the plugin."""
from __future__ import annotations

from typing import Optional

PARSE_MODE_OPTIONS = ["html", "markdown", "markdownv2", "none"]
"""Supported parse mode aliases exposed to configuration/UI layers."""

PARSE_MODE_OPTION_LABELS = {
    "html": "HTML",
    "markdown": "Markdown",
    "markdownv2": "Markdown V2",
    "none": "纯文本",
}
"""Human readable labels for the parse mode options."""

DEFAULT_PARSE_MODE_ALIAS = PARSE_MODE_OPTIONS[0]
"""Default parse mode alias used when none is provided."""


def ensure_parse_mode_alias(value: Optional[str]) -> str:
    """Return a normalised parse mode alias recognised by the plugin."""
    alias = str(value or "").strip().lower()
    if alias in PARSE_MODE_OPTIONS:
        return alias
    return DEFAULT_PARSE_MODE_ALIAS


def resolve_parse_mode(value: Optional[str], *, default: Optional[str] = None) -> Optional[str]:
    """
    Convert a user provided parse mode alias into the Telegram API constant.

    The helper understands the aliases we surface in the UI (``html``, ``markdown``,
    ``markdownv2`` and ``none``) as well as the canonical Telegram constants.
    Unknown values fall back to ``default`` so callers can decide whether to keep
    the previous value or reset to ``None``.
    """

    if value is None:
        return default

    alias = str(value).strip()
    if not alias:
        return default

    lowered = alias.lower()
    if lowered in {"", "plain", "text", "none", "disabled"}:
        return None

    mapping = {
        "html": "HTML",
        "markdown": "Markdown",
        "md": "Markdown",
        "markdownv2": "MarkdownV2",
        "mdv2": "MarkdownV2",
    }
    if lowered in mapping:
        return mapping[lowered]

    if alias in {"HTML", "Markdown", "MarkdownV2"}:
        return alias

    return default


DEFAULT_PARSE_MODE = resolve_parse_mode(DEFAULT_PARSE_MODE_ALIAS, default="HTML")
"""Default Telegram parse mode constant corresponding to ``DEFAULT_PARSE_MODE_ALIAS``."""


__all__ = [
    "DEFAULT_PARSE_MODE",
    "DEFAULT_PARSE_MODE_ALIAS",
    "PARSE_MODE_OPTION_LABELS",
    "PARSE_MODE_OPTIONS",
    "ensure_parse_mode_alias",
    "resolve_parse_mode",
]
