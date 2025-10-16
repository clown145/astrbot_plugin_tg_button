"""Shared helpers for local Telegram message actions."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from ..parse_mode import (
    DEFAULT_PARSE_MODE,
    DEFAULT_PARSE_MODE_ALIAS,
    PARSE_MODE_OPTION_LABELS,
    PARSE_MODE_OPTIONS,
    ensure_parse_mode_alias,
    resolve_parse_mode,
)

__all__ = [
    "DEFAULT_PARSE_MODE_ALIAS",
    "PARSE_MODE_OPTION_LABELS",
    "PARSE_MODE_OPTIONS",
    "coerce_parse_mode_for_api",
    "ensure_parse_mode_alias",  # re-export for convenience
    "ensure_parse_mode_alias_or_default",
    "open_binary_file",
    "require_client",
]


@contextmanager
def open_binary_file(path: str, description: str) -> Iterator[Any]:
    """Open *path* as binary stream, raising a RuntimeError on failure."""
    file_path = Path(path)
    if not file_path.is_file():
        raise RuntimeError(f"{description}文件不存在: {path}")

    try:
        with file_path.open("rb") as handle:
            yield handle
    except OSError as exc:  # pragma: no cover - defensive logging wrapper
        raise RuntimeError(f"读取{description}文件失败: {exc}") from exc


def require_client(plugin: Any) -> Any:
    """Fetch the Telegram client from *plugin* or raise a RuntimeError."""
    client = plugin._get_telegram_client()  # noqa: SLF001 - private helper access is expected
    if not client:
        raise RuntimeError("无法获取 Telegram 客户端实例。")
    return client


def coerce_parse_mode_for_api(value: Optional[str]) -> Optional[str]:
    """Convert a parse mode alias into the Telegram constant used by the API."""
    alias = ensure_parse_mode_alias(value)
    return resolve_parse_mode(alias, default=DEFAULT_PARSE_MODE)


def ensure_parse_mode_alias_or_default(value: Optional[str]) -> str:
    """Normalise a parse mode alias, falling back to the plugin default."""
    return ensure_parse_mode_alias(value)
