# local_actions/edit_message_text.py

from typing import TYPE_CHECKING, Dict, Any

if TYPE_CHECKING:
    from ..main import DynamicButtonFrameworkPlugin

from ..telegram_format import build_parse_mode_input, map_to_telegram_parse_mode

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
        build_parse_mode_input(
            description="更新消息时使用的 Telegram 解析模式。",
            default="html",
        ),
    ],
    "outputs": [
        {
            "name": "message_id",
            "type": "integer",
            "description": "成功更新后，消息的唯一ID。",
        }
    ],
}


# --- 动作执行逻辑 ---
async def execute(
    plugin: "DynamicButtonFrameworkPlugin",
    chat_id: str,
    message_id: int,
    text: str,
    parse_mode: str = "html",
) -> Dict[str, Any]:
    """
    立即执行更新消息文本的操作，并返回 message_id。
    """
    # 1. 获取 Telegram 客户端
    client = plugin._get_telegram_client()
    if not client:
        raise RuntimeError("无法获取 Telegram 客户端实例。")

    # 2. 调用 API 更新消息
    tg_parse_mode = map_to_telegram_parse_mode(parse_mode)
    kwargs: Dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
    }
    if tg_parse_mode:
        kwargs["parse_mode"] = tg_parse_mode

    try:
        await client.edit_message_text(**kwargs)
    except Exception as e:
        plugin.logger.error(f"更新消息时出错: {e}", exc_info=True)
        raise RuntimeError(f"调用 Telegram API 更新消息失败: {e}")

    # 3. 如果成功，返回 message_id 以便后续节点使用
    return {"message_id": message_id}
