"""
tg_button 插件的命令处理逻辑。
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from astrbot.api.event import AstrMessageEvent, filter

# 类型提示的循环导入保护
if TYPE_CHECKING:
    from .main import DynamicButtonFrameworkPlugin

# 从 telegram 导入，可能为 None
try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
except ImportError:
    InlineKeyboardButton, InlineKeyboardMarkup = None, None


async def send_menu(plugin: "DynamicButtonFrameworkPlugin", event: AstrMessageEvent):
    """显示交互式按钮菜单的逻辑。"""
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
