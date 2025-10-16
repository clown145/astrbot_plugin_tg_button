from typing import TYPE_CHECKING, Dict, Any

from ._message_utils import (
    DEFAULT_PARSE_MODE_ALIAS,
    PARSE_MODE_OPTION_LABELS,
    PARSE_MODE_OPTIONS,
    coerce_parse_mode_for_api,
    open_binary_file,
    require_client,
)

try:
    from telegram import InputMediaAudio, InputMediaPhoto
except ImportError:  # pragma: no cover - optional dependency guard
    InputMediaPhoto, InputMediaAudio = None, None

if TYPE_CHECKING:
    from ..main import DynamicButtonFrameworkPlugin

# --- 动作元数据 ---
ACTION_METADATA = {
    "id": "edit_message_media",
    "name": "编辑媒体消息",
    "description": "更新一条已存在媒体消息的图片/语音，和/或它的说明文字。不能将纯文本消息转为媒体消息。",
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
            "description": "要编辑的消息的唯一 ID。",
        },
        {
            "name": "text",
            "type": "string",
            "required": False,
            "description": "新的说明文字 (caption)。如果只提供此项，则只更新文字。",
        },
        {
            "name": "image_source",
            "type": "string",
            "required": False,
            "description": "要替换的**本地图片文件路径**。如果同时提供图片和语音，优先使用图片。",
        },
        {
            "name": "voice_source",
            "type": "string",
            "required": False,
            "description": "要替换的**本地语音文件路径**。",
        },
        {
            "name": "parse_mode",
            "type": "string",
            "required": False,
            "default": DEFAULT_PARSE_MODE_ALIAS,
            "description": "更新说明文字时使用的 Telegram 解析模式。",
            "enum": PARSE_MODE_OPTIONS,
            "enum_labels": PARSE_MODE_OPTION_LABELS,
        },
    ],
    "outputs": [
        {
            "name": "message_id",
            "type": "integer",
            "description": "成功编辑后，消息的唯一ID。",
        }
    ],
}


async def execute(
    plugin: "DynamicButtonFrameworkPlugin",
    chat_id: str,
    message_id: int,
    text: str = None,
    image_source: str = None,
    voice_source: str = None,
    parse_mode: str = DEFAULT_PARSE_MODE_ALIAS,
) -> Dict[str, Any]:
    """执行编辑媒体消息的操作。"""
    client = require_client(plugin)
    telegram_parse_mode = coerce_parse_mode_for_api(parse_mode)

    if not any([text, image_source, voice_source]):
        plugin.logger.warning(
            "edit_message_media: 未提供任何有效输入（文本、图片或语音），操作已跳过。"
        )
        return {}

    if not InputMediaPhoto:
        raise RuntimeError("Telegram 库未完整安装，缺少 InputMedia* 类型。")

    try:
        if image_source:
            with open_binary_file(image_source, "图片") as photo_file:
                media_payload = InputMediaPhoto(
                    media=photo_file,
                    caption=text or None,
                    parse_mode=telegram_parse_mode,
                )
                await client.edit_message_media(
                    chat_id=chat_id,
                    message_id=message_id,
                    media=media_payload,
                )
        elif voice_source:
            if not InputMediaAudio:
                raise RuntimeError("Telegram 库缺少 InputMediaAudio 类型，无法更新语音。")
            with open_binary_file(voice_source, "语音") as voice_file:
                media_payload = InputMediaAudio(
                    media=voice_file,
                    caption=text or None,
                    parse_mode=telegram_parse_mode,
                )
                await client.edit_message_media(
                    chat_id=chat_id,
                    message_id=message_id,
                    media=media_payload,
                )
        elif text is not None:
            await client.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=text,
                parse_mode=telegram_parse_mode,
            )
    except Exception as e:  # pragma: no cover - depends on Telegram connectivity
        plugin.logger.error(f"编辑媒体消息时出错: {e}", exc_info=True)
        raise RuntimeError(f"调用 Telegram API 编辑媒体消息失败: {e}")

    return {"message_id": message_id}
