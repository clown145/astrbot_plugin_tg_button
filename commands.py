"""
Command handling logic for the tg_button plugin.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from astrbot.api.event import AstrMessageEvent, filter

# Guard for circular import for type hinting
if TYPE_CHECKING:
    from .main import DynamicButtonFrameworkPlugin

# Imports from telegram, which might be None
try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
except ImportError:
    InlineKeyboardButton, InlineKeyboardMarkup = None, None


async def send_menu(plugin: "DynamicButtonFrameworkPlugin", event: AstrMessageEvent):
    """Logic for displaying the interactive button menu."""
    if plugin.webui_exclusive:
        yield event.plain_result("WebUI 独占模式已启用，请通过 WebUI 操作按钮。")
        return
    if event.get_platform_name() != "telegram":
        yield event.plain_result("当前仅支持 Telegram 平台。")
        return
    if not InlineKeyboardMarkup or not InlineKeyboardButton:
        yield event.plain_result("python-telegram-bot 库不可用，无法发送菜单。")
        return

    snapshot = await plugin.button_store.get_snapshot()
    markup, header = plugin._build_menu_markup("root", snapshot)

    if not markup:
        yield event.plain_result("当前未配置任何按钮。")
        return

    client = plugin._get_telegram_client()
    if not client:
        yield event.plain_result("无法获取 Telegram 客户端，请检查日志。")
        return

    chat_id_str = event.get_group_id() or event.get_sender_id()
    if not chat_id_str:
        yield event.plain_result("无法确定会话上下文。")
        return

    chat_id, thread_id = plugin._split_chat_id(chat_id_str)

    try:
        await client.send_message(
            chat_id=chat_id,
            text=header or plugin.menu_header,
            reply_markup=markup,
            message_thread_id=thread_id,
        )
    except Exception as exc:
        plugin.logger.error(f"发送自定义菜单失败: {exc}", exc_info=True)
        yield event.plain_result("发送菜单时出错，请查看后台日志。")
        return
    event.stop_event()


async def bind_button(plugin: "DynamicButtonFrameworkPlugin", event: AstrMessageEvent):
    """Logic for binding a new button via command."""
    if plugin.webui_exclusive:
        yield event.plain_result("WebUI 独占模式已启用，请在 WebUI 中管理按钮。")
        return

    args = event.message_str.strip().split()
    if len(args) < 4:
        yield event.plain_result("格式错误！\n示例: /bind 搜索 指令 search something")
        return

    _, *actual = args
    type_keywords_map = {
        "指令": "command",
        "command": "command",
        "网址": "url",
        "url": "url",
        "web": "web_app",
        "webapp": "web_app",
    }
    btn_type = None
    type_index = -1
    for idx, part in enumerate(actual):
        key = part.lower()
        if key in type_keywords_map and idx > 0 and idx < len(actual) - 1:
            btn_type = type_keywords_map[key]
            type_index = idx
            break

    if not btn_type:
        yield event.plain_result("格式错误！类型必须是 指令/command 或 网址/url 或 web。")
        return

    text = " ".join(actual[:type_index])
    value = " ".join(actual[type_index + 1 :])

    if not text or not value:
        yield event.plain_result("格式错误！请提供按钮文字与绑定内容。")
        return

    await plugin.button_store.upsert_simple_button(text, btn_type, value)
    yield event.plain_result(f"按钮 '{text}' 已成功绑定为 {btn_type}。")


async def unbind_button(plugin: "DynamicButtonFrameworkPlugin", event: AstrMessageEvent):
    """Logic for unbinding a button via command."""
    if plugin.webui_exclusive:
        yield event.plain_result("WebUI 独占模式已启用，请在 WebUI 中管理按钮。")
        return

    args = event.message_str.strip().split()
    if len(args) < 2:
        yield event.plain_result("请输入要解绑的按钮文本。")
        return

    text = " ".join(args[1:])
    removed = await plugin.button_store.remove_button_by_text(text)
    if removed:
        yield event.plain_result(f"按钮 '{text}' 已成功解绑。")
    else:
        yield event.plain_result(f"未找到名为 '{text}' 的按钮。")
