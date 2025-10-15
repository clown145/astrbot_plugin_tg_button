"""
astrbot_plugin_tg_button 插件的配置加载与管理。
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
    "allow_script_uploads": False,
    "secure_script_upload_password": "",
}


def _load_raw_config() -> Dict[str, Any]:
    """从磁盘加载原始配置文件。"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as fp:
            return json.load(fp)
    except FileNotFoundError:
        logger.warning("按钮框架插件的配置文件未找到，将使用默认值。")
    except json.JSONDecodeError as exc:
        logger.error(f"解析配置文件 {CONFIG_PATH.name} 失败: {exc}，将使用默认值。")
    return {}


def _ensure_string(value: Any, default: str) -> str:
    """将值强制转换为字符串。"""
    if isinstance(value, str):
        return value
    if value is None:
        return default
    return str(value)


def _coerce_bool(value: Any, default: bool) -> bool:
    """将值强制转换为布尔值。"""
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
    """将值强制转换为整数。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_settings(raw: Dict[str, Any]) -> Dict[str, Any]:
    """根据原始配置和默认值构建最终的设置字典。"""
    settings = dict(CONFIG_DEFAULTS)
    if raw:
        settings.update(raw)

    settings["menu_command"] = _ensure_string(
        settings.get("menu_command"), CONFIG_DEFAULTS["menu_command"]
    )
    settings["menu_header_text"] = _ensure_string(
        settings.get("menu_header_text"), CONFIG_DEFAULTS["menu_header_text"]
    )
    settings["webui_enabled"] = _coerce_bool(
        raw.get("webui_enabled", settings.get("webui_enabled")),
        CONFIG_DEFAULTS["webui_enabled"],
    )
    settings["webui_port"] = _coerce_int(
        settings.get("webui_port"), CONFIG_DEFAULTS["webui_port"]
    )
    settings["webui_host"] = _ensure_string(
        settings.get("webui_host"), CONFIG_DEFAULTS["webui_host"]
    )
    settings["webui_exclusive"] = _coerce_bool(
        raw.get("webui_exclusive", settings.get("webui_exclusive")),
        CONFIG_DEFAULTS["webui_exclusive"],
    )
    settings["webui_auth_token"] = _ensure_string(
        settings.get("webui_auth_token"), CONFIG_DEFAULTS["webui_auth_token"]
    )
    settings["allow_script_uploads"] = _coerce_bool(
        settings.get("allow_script_uploads"), CONFIG_DEFAULTS["allow_script_uploads"]
    )
    settings["secure_script_upload_password"] = _ensure_string(
        settings.get("secure_script_upload_password"),
        CONFIG_DEFAULTS["secure_script_upload_password"],
    )
    return settings


# 在模块导入时加载初始设置，以便装饰器可以使用 MENU_COMMAND。
# 这部分代码仅在模块首次导入时执行一次。
raw_config = _load_raw_config()
INITIAL_SETTINGS = build_settings(raw_config)
MENU_COMMAND = INITIAL_SETTINGS["menu_command"]
