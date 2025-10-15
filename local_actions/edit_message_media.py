# local_actions/edit_message_media.py

from typing import TYPE_CHECKING, Dict, Any

# 导入 Telegram 媒体类型
try:
    from telegram import InputMediaPhoto, InputMediaAudio
except ImportError:
    # 提供回退，以防库未安装
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
    ],
    "outputs": [
        {
            "name": "message_id",
            "type": "integer",
            "description": "成功编辑后，消息的唯一ID。",
        }
    ],
}


# --- 动作执行逻辑 ---
async def execute(
    plugin: "DynamicButtonFrameworkPlugin",
    chat_id: str,
    message_id: int,
    text: str = None,
    image_source: str = None,
    voice_source: str = None,
) -> Dict[str, Any]:
    """
    执行编辑媒体消息的操作。
    """
    # 1. 获取 Telegram 客户端和必要检查
    client = plugin._get_telegram_client()
    if not client:
        raise RuntimeError("无法获取 Telegram 客户端实例。")
    if not any([text, image_source, voice_source]):
        plugin.logger.warning("edit_message_media: 未提供任何有效输入（文本、图片或语音），操作已跳过。")
        return {}
    if not InputMediaPhoto:
         raise RuntimeError("Telegram 库未完整安装，缺少 InputMediaPhoto 等类型。")


    # 2. 根据输入决定执行何种操作
    try:
        # --- 情况 A: 需要替换媒体 ---
        if image_source or voice_source:
            media_payload = None
            # 优先使用图片
            if image_source:
                with open(image_source, "rb") as photo_file:
                    media_payload = InputMediaPhoto(media=photo_file, caption=text)
            elif voice_source:
                with open(voice_source, "rb") as voice_file:
                    media_payload = InputMediaAudio(media=voice_file, caption=text)

            await client.edit_message_media(
                chat_id=chat_id,
                message_id=message_id,
                media=media_payload
            )

        # --- 情况 B: 只更新说明文字 ---
        elif text is not None:
            await client.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=text
            )

    except Exception as e:
        plugin.logger.error(f"编辑媒体消息时出错: {e}", exc_info=True)
        raise RuntimeError(f"调用 Telegram API 编辑媒体消息失败: {e}")

    # 3. 如果成功，返回 message_id
    return {"message_id": message_id}
