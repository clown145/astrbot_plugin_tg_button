# local_actions/send_message.py

from typing import TYPE_CHECKING, Any, Dict

from ._message_utils import (
    DEFAULT_PARSE_MODE_ALIAS,
    PARSE_MODE_OPTION_LABELS,
    PARSE_MODE_OPTIONS,
    coerce_parse_mode_for_api,
    open_binary_file,
    require_client,
)

if TYPE_CHECKING:
    from ..main import DynamicButtonFrameworkPlugin

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
        {
            "name": "parse_mode",
            "type": "string",
            "required": False,
            "default": DEFAULT_PARSE_MODE_ALIAS,
            "description": "发送文本或说明文字时使用的 Telegram 解析模式。",
            "enum": PARSE_MODE_OPTIONS,
            "enum_labels": PARSE_MODE_OPTION_LABELS,
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


async def execute(
    plugin: "DynamicButtonFrameworkPlugin",
    chat_id: str,
    text: str = "",
    image_source: str = None,
    voice_source: str = None,
    parse_mode: str = DEFAULT_PARSE_MODE_ALIAS,
) -> Dict[str, Any]:
    """立即执行发送消息的操作，并返回 message_id。"""
    client = require_client(plugin)
    telegram_parse_mode = coerce_parse_mode_for_api(parse_mode)

    caption = text or ""
    sent_message = None

    try:
        if image_source:
            with open_binary_file(image_source, "图片") as photo_payload:
                sent_message = await client.send_photo(
                    chat_id=chat_id,
                    photo=photo_payload,
                    caption=caption or None,
                    parse_mode=telegram_parse_mode,
                )
        elif voice_source:
            with open_binary_file(voice_source, "语音") as voice_payload:
                sent_message = await client.send_voice(
                    chat_id=chat_id,
                    voice=voice_payload,
                    caption=caption or None,
                    parse_mode=telegram_parse_mode,
                )
        elif caption:
            sent_message = await client.send_message(
                chat_id=chat_id,
                text=caption,
                parse_mode=telegram_parse_mode,
            )
        else:
            return {}

    except Exception as e:  # pragma: no cover - depends on Telegram connectivity
        plugin.logger.error(f"发送消息时出错: {e}", exc_info=True)
        raise RuntimeError(f"调用 Telegram API 发送消息失败: {e}")

    if sent_message and hasattr(sent_message, "message_id"):
        return {"message_id": sent_message.message_id}

    return {}
