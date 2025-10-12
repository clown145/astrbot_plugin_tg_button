"""
Configuration loading and management for the astra_plugin_tg_button.
"""
import json
from pathlib import Path
from typing import Any, Dict

from astrbot.api import logger

PLUGIN_NAME = "astrbot_plugin_tg_button"
CONFIG_PATH = Path(f"data/config/{PLUGIN_NAME}_config.json")

CONFIG_DEFAULTS: Dict[str, Any] = {
    "menu_command": "menu",
    "menu_header_text": "请选择功能",
    "webui_enabled": False,
    "webui_port": 17861,
    "webui_host": "127.0.0.1",
    "webui_exclusive": True,
    "webui_auth_token": "",
}

def _load_raw_config() -> Dict[str, Any]:
    """Loads the raw config file from disk."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as fp:
            return json.load(fp)
    except FileNotFoundError:
        logger.warning("按钮框架插件的配置文件未找到，将使用默认值。")
    except json.JSONDecodeError as exc:
        logger.error(f"解析配置文件 {CONFIG_PATH.name} 失败: {exc}，将使用默认值。")
    return {}


def _ensure_string(value: Any, default: str) -> str:
    """Coerces a value to a string."""
    if isinstance(value, str):
        return value
    if value is None:
        return default
    return str(value)


def _coerce_bool(value: Any, default: bool) -> bool:
    """Coerces a value to a boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _coerce_int(value: Any, default: int) -> int:
    """Coerces a value to an integer."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_settings(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Builds the final settings dictionary from raw config and defaults."""
    settings = dict(CONFIG_DEFAULTS)
    if raw:
        settings.update(raw)

    settings["menu_command"] = _ensure_string(settings.get("menu_command"), CONFIG_DEFAULTS["menu_command"])
    settings["menu_header_text"] = _ensure_string(settings.get("menu_header_text"), CONFIG_DEFAULTS["menu_header_text"])
    settings["webui_enabled"] = _coerce_bool(raw.get("webui_enabled", settings.get("webui_enabled")), CONFIG_DEFAULTS["webui_enabled"])
    settings["webui_port"] = _coerce_int(settings.get("webui_port"), CONFIG_DEFAULTS["webui_port"])
    settings["webui_host"] = _ensure_string(settings.get("webui_host"), CONFIG_DEFAULTS["webui_host"])
    settings["webui_exclusive"] = _coerce_bool(raw.get("webui_exclusive", settings.get("webui_exclusive")), CONFIG_DEFAULTS["webui_exclusive"])
    settings["webui_auth_token"] = _ensure_string(settings.get("webui_auth_token"), CONFIG_DEFAULTS["webui_auth_token"])
    return settings

# Load initial settings at module import time to make MENU_COMMAND available for decorators.
# This part is executed only once when the module is first imported.
raw_config = _load_raw_config()
INITIAL_SETTINGS = build_settings(raw_config)
MENU_COMMAND = INITIAL_SETTINGS["menu_command"]
