# local_actions/send_message.py

from typing import TYPE_CHECKING, Dict, Any, List

if TYPE_CHECKING:
    from ..main import DynamicButtonFrameworkPlugin
    from ..actions import RuntimeContext

# --- 动作元数据 (新版) ---
ACTION_METADATA = {
    "id": "send_message",
    "name": "发送新消息",
    "description": "立即发送一条全新的消息，并输出 message_id。可包含文本和单个媒体文件（图片或语音）。",
    "inputs": [
        {
            "name": "text",
            "type": "string",
            "required": False,
            "description": "要发送的文本内容。可以与图片或语音一起作为说明文字发送。",
        },
        {
            "name": "image_source",
            "type": "string",
            "required": False,
            "description": "要发送的图片的**本地文件路径**。请与 `cache_from_url` 动作配合使用来下载网络图片。",
        },
        {
            "name": "voice_source",
            "type": "string",
            "required": False,
            "description": "要发送的语音的**本地文件路径**。通常来自 `cache_from_url` 动作的输出。",
        },
        {
            "name": "chat_id",
            "type": "string",
            "required": True,
            "description": "要发送到的目标聊天 ID。通常从工作流的运行时变量 `runtime.chat_id` 获取。",
        },
    ],
    "outputs": [
        {
            "name": "message_id",
            "type": "integer",
            "description": "成功发送后，新消息的唯一ID。",
        }
    ],
}


# --- 动作执行逻辑---
async def execute(
    plugin: "DynamicButtonFrameworkPlugin",
    chat_id: str,
    text: str = None,
    image_source: str = None,
    voice_source: str = None,
) -> Dict[str, Any]:
    """
    【已重构】立即执行发送消息的操作，并返回 message_id。
    """
    # 1. 获取 Telegram 客户端
    client = plugin._get_telegram_client()
    if not client:
        # 在真实执行环境中，最好是通过抛出异常来中断工作流，但这里为了简单，返回一个错误指示
        # 注意：ActionExecutor 会捕获这个异常并报告错误
        raise RuntimeError("无法获取 Telegram 客户端实例。")

    # 2. 准备消息内容
    caption = text or ""
    sent_message = None

    # 3. 根据内容调用不同的 API
    try:
        if image_source:
            with open(image_source, "rb") as photo_payload:
                sent_message = await client.send_photo(
                    chat_id=chat_id, photo=photo_payload, caption=caption
                )
        elif voice_source:
            with open(voice_source, "rb") as voice_payload:
                sent_message = await client.send_voice(
                    chat_id=chat_id, voice=voice_payload, caption=caption
                )
        elif caption:
            sent_message = await client.send_message(chat_id=chat_id, text=caption)
        else:
            # 没有发送任何内容，可以选择静默返回或报错
            return {}  # 返回空字典，表示没有输出

    except Exception as e:
        plugin.logger.error(f"发送消息时出错: {e}", exc_info=True)
        raise RuntimeError(f"调用 Telegram API 发送消息失败: {e}")

    # 4. 如果发送成功，提取并返回 message_id
    if sent_message and hasattr(sent_message, "message_id"):
        message_id = sent_message.message_id
        # 按新规范，将输出变量直接放在返回字典的顶层
        return {"message_id": message_id}

    return {}
