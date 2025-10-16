# local_actions/edit_message_text.py

from typing import TYPE_CHECKING, Dict, Any

from ._message_utils import (
    DEFAULT_PARSE_MODE_ALIAS,
    PARSE_MODE_OPTION_LABELS,
    PARSE_MODE_OPTIONS,
    coerce_parse_mode_for_api,
    require_client,
)

if TYPE_CHECKING:
    from ..main import DynamicButtonFrameworkPlugin

# --- 动作元数据 ---
ACTION_METADATA = {
    "id": "edit_message_text",
    "name": "编辑消息文本",
    "description": "通过消息 ID 更新一条已存在消息的文本内容。可用于动态显示状态或结果。",
    "inputs": [
        {
            "name": "chat_id",
            "type": "string",
            "required": True,
            "description": "要更新消息所在的聊天 ID。通常来自工作流的运行时变量 `runtime.chat_id`。",
        },
        {
            "name": "message_id",
            "type": "integer",
            "required": True,
            "description": "要更新的消息的唯一 ID。通常来自 `send_message` 动作的输出。",
        },
        {
            "name": "text",
            "type": "string",
            "required": True,
            "description": "要更新到的新文本内容。",
        },
        {
            "name": "parse_mode",
            "type": "string",
            "required": False,
            "default": DEFAULT_PARSE_MODE_ALIAS,
            "description": "渲染文本时使用的 Telegram 解析模式。",
            "enum": PARSE_MODE_OPTIONS,
            "enum_labels": PARSE_MODE_OPTION_LABELS,
        },
    ],
    "outputs": [
        {
            "name": "message_id",
            "type": "integer",
            "description": "成功更新后，消息的唯一ID。",
        }
    ],
}


async def execute(
    plugin: "DynamicButtonFrameworkPlugin",
    chat_id: str,
    message_id: int,
    text: str,
    parse_mode: str = DEFAULT_PARSE_MODE_ALIAS,
) -> Dict[str, Any]:
    """立即执行更新消息文本的操作，并返回 message_id。"""
    client = require_client(plugin)
    telegram_parse_mode = coerce_parse_mode_for_api(parse_mode)

    try:
        await client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode=telegram_parse_mode,
        )
    except Exception as e:  # pragma: no cover - depends on Telegram connectivity
        plugin.logger.error(f"更新消息时出错: {e}", exc_info=True)
        raise RuntimeError(f"调用 Telegram API 更新消息失败: {e}")

    return {"message_id": message_id}
