# local_actions/delete_message.py

from typing import TYPE_CHECKING, Dict, Any

if TYPE_CHECKING:
    from ..main import DynamicButtonFrameworkPlugin

# --- 动作元数据 ---
ACTION_METADATA = {
    "id": "delete_message",
    "name": "删除消息",
    "description": "根据提供的 chat_id 和 message_id 删除一条指定的消息。",
    "inputs": [
        {
            "name": "chat_id",
            "type": "string",
            "required": True,
            "description": "消息所在的聊天 ID。",
        },
        {
            "name": "message_id",
            "type": "integer",
            "required": True,
            "description": "要删除的消息的唯一 ID。",
        },
    ],
    "outputs": [],
}


# --- 动作执行逻辑 ---
async def execute(
    plugin: "DynamicButtonFrameworkPlugin",
    chat_id: str,
    message_id: int,
) -> Dict[str, Any]:
    """
    执行删除消息的操作。
    """
    # 1. 获取 Telegram 客户端
    client = plugin._get_telegram_client()
    if not client:
        raise RuntimeError("无法获取 Telegram 客户端实例。")

    # 2. 调用 API 删除消息
    try:
        await client.delete_message(
            chat_id=chat_id,
            message_id=message_id,
        )
    except Exception as e:
        # 如果消息已经被删除或不存在，API 可能会报错。记录警告但不必中断工作流。
        plugin.logger.warning(f"删除消息时出错 (可能消息已不存在): {e}")
        # 不向上抛出异常，让工作流可以继续执行

    # 3. 此动作不产生输出
    return {}
