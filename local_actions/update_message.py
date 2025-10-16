from typing import Dict

from ._message_utils import (
    DEFAULT_PARSE_MODE_ALIAS,
    PARSE_MODE_OPTION_LABELS,
    PARSE_MODE_OPTIONS,
    ensure_parse_mode_alias_or_default,
)

ACTION_METADATA = {
    "id": "update_message",
    "name": "更新菜单标题",
    "description": "使用输入的文本更新当前菜单的标题文本。",
    "inputs": [
        {"name": "text", "type": "string", "description": "要显示的新的菜单标题。"},
        {
            "name": "parse_mode",
            "type": "string",
            "required": False,
            "default": DEFAULT_PARSE_MODE_ALIAS,
            "description": "渲染菜单标题时使用的 Telegram 解析模式。",
            "enum": PARSE_MODE_OPTIONS,
            "enum_labels": PARSE_MODE_OPTION_LABELS,
        },
    ],
    "outputs": [],
}


async def execute(text: str, parse_mode: str = DEFAULT_PARSE_MODE_ALIAS) -> Dict[str, str]:
    """将输入的文本作为 new_text 返回以更新菜单标题。"""
    normalised_mode = ensure_parse_mode_alias_or_default(parse_mode)
    result: Dict[str, str] = {"new_text": text}
    if text:
        result["parse_mode"] = normalised_mode
    return result
