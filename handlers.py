"""
Handles Telegram Callback Query logic for the tg_button plugin.
"""
from __future__ import annotations
import asyncio
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

# Guard for circular import for type hinting
if TYPE_CHECKING:
    from .main import DynamicButtonFrameworkPlugin

def async_handle_callback_query(plugin: "DynamicButtonFrameworkPlugin", update: Any, _context: Any):
    """Asynchronously dispatches the callback query handling to a new task."""
    # Run the actual handler in a new task to avoid blocking the caller
    asyncio.create_task(handle_callback_query(plugin, update, _context))

async def handle_callback_query(plugin: "DynamicButtonFrameworkPlugin", update: Any, _context: Any) -> None:
    """Main entry point for handling callback queries."""
    query = getattr(update, "callback_query", None)
    if not query or not query.data:
        return

    if plugin.webui_exclusive:
        await query.answer("WebUI 独占模式已启用，请通过 WebUI 操作。", show_alert=True)
        return

    data = query.data
    try:
        if data.startswith(plugin.CALLBACK_PREFIX_COMMAND):
            button_id = data[len(plugin.CALLBACK_PREFIX_COMMAND):]
            await handle_command_button(plugin, query, button_id)
        elif data.startswith(plugin.CALLBACK_PREFIX_MENU):
            menu_id = data[len(plugin.CALLBACK_PREFIX_MENU):] or "root"
            await handle_menu_navigation(plugin, query, menu_id)
        elif data.startswith(plugin.CALLBACK_PREFIX_BACK):
            menu_id = data[len(plugin.CALLBACK_PREFIX_BACK):] or "root"
            await handle_menu_navigation(plugin, query, menu_id)
        elif data.startswith(plugin.CALLBACK_PREFIX_ACTION):
            button_id = data[len(plugin.CALLBACK_PREFIX_ACTION):]
            await handle_action_button(plugin, query, button_id)
        else:
            await query.answer()
    except Exception as exc:
        plugin.logger.error(f"处理按钮回调时出错: {exc}", exc_info=True)
        await query.answer("处理失败，请稍后重试。", show_alert=True)

async def handle_command_button(plugin: "DynamicButtonFrameworkPlugin", query: Any, button_id: str) -> None:
    snapshot = await plugin.button_store.get_snapshot()
    button = snapshot.buttons.get(button_id)
    if not button:
        await query.answer("按钮已不存在。", show_alert=True)
        return

    command_text = button.payload.get("command")
    if not command_text:
        await query.answer("按钮未绑定指令。", show_alert=True)
        return

    await query.answer()
    await plugin._dispatch_command(query, command_text)

async def handle_menu_navigation(plugin: "DynamicButtonFrameworkPlugin", query: Any, target_menu_id: str) -> None:
    snapshot = await plugin.button_store.get_snapshot()
    markup, header = plugin._build_menu_markup(target_menu_id or "root", snapshot)
    if not markup:
        await query.answer("目标菜单不存在。", show_alert=True)
        return

    client = plugin._get_telegram_client()
    if not client:
        await query.answer("无法获取 Telegram 客户端。", show_alert=True)
        return

    message = query.message
    if not message:
        await query.answer()
        return

    try:
        await client.edit_message_text(
            chat_id=message.chat.id,
            message_id=message.message_id,
            text=header or plugin.menu_header,
            reply_markup=markup,
        )
    except Exception as exc:
        plugin.logger.error(f"切换菜单时出错: {exc}", exc_info=True)
        await query.answer("切换失败，请稍后再试。", show_alert=True)
        return
    await query.answer()


async def handle_action_button(plugin: "DynamicButtonFrameworkPlugin", query: Any, button_id: str) -> None:
    from .actions import RuntimeContext

    snapshot = await plugin.button_store.get_snapshot()
    button = snapshot.buttons.get(button_id)
    if not button:
        await query.answer("按钮已不存在。", show_alert=True)
        return

    action_id = button.payload.get("action_id")
    if not action_id:
        await query.answer("未绑定动作。", show_alert=True)
        return

    action = snapshot.actions.get(action_id)
    if not action:
        await query.answer("动作不存在。", show_alert=True)
        return

    menu = plugin._find_menu_for_button(snapshot, button_id)
    if not menu:
        await query.answer("未找到按钮所属菜单。", show_alert=True)
        return

    message = query.message
    if not message:
        await query.answer("缺少消息上下文。", show_alert=True)
        return

    replied_message = getattr(message, "reply_to_message", None)
    replied_text = getattr(replied_message, "text", "") if replied_message else ""
    replied_caption = getattr(replied_message, "caption", "") if replied_message else ""

    runtime = RuntimeContext(
        chat_id=str(message.chat.id),
        message_id=message.message_id,
        thread_id=getattr(message, "message_thread_id", None),
        user_id=str(query.from_user.id) if query.from_user else None,
        username=query.from_user.username if query.from_user else None,
        full_name=query.from_user.full_name if query.from_user else None,
        callback_data=query.data,
        variables={
            "menu_id": menu.id,
            "menu_name": menu.name,
            "button_payload": button.payload,
            "message_text": getattr(message, "text", ""),
            "message_caption": getattr(message, "caption", ""),
            "replied_text": replied_text or replied_caption,
        },
    )

    result = await plugin.action_executor.execute(
        action.to_dict(),
        button=button.to_dict(),
        menu=menu.to_dict(),
        runtime=runtime,
    )

    if not result.success:
        await query.answer(result.error or "动作执行失败。", show_alert=True)
        return

    client = plugin._get_telegram_client()
    if not client:
        await query.answer("动作已执行，但无法更新消息。", show_alert=True)
        return

    target_menu_id = result.next_menu_id or menu.id
    next_snapshot = await plugin.button_store.get_snapshot()
    overrides_map: Dict[str, Dict[str, Any]] = {}
    if result.button_overrides:
        overrides_map = plugin._resolve_button_overrides(next_snapshot, menu, result.button_overrides, button_id)

    if result.button_title:
        overrides_map.setdefault(button_id, {}).setdefault('text', result.button_title)

    markup, header = plugin._build_menu_markup(target_menu_id, next_snapshot, overrides=overrides_map)
    reply_markup = markup if markup else None
    text_to_use = result.new_text or header or getattr(message, "text", plugin.menu_header)

    if result.should_edit_message or result.new_text:
        if text_to_use == message.text and message.reply_markup == reply_markup:
            await query.answer()
            return

        try:
            await client.edit_message_text(
                chat_id=message.chat.id,
                message_id=message.message_id,
                text=text_to_use,
                reply_markup=reply_markup,
                parse_mode=result.parse_mode,
            )
        except Exception as exc:
            plugin.logger.error(f"执行动作后更新消息失败: {exc}", exc_info=True)
            await query.answer("动作执行成功，但更新消息失败。", show_alert=True)
            return
    elif reply_markup:
        if message.reply_markup == reply_markup:
            await query.answer()
            return

        try:
            await client.edit_message_reply_markup(
                chat_id=message.chat.id,
                message_id=message.message_id,
                reply_markup=reply_markup,
            )
        except Exception as exc:
            plugin.logger.error(f"更新按钮布局失败: {exc}", exc_info=True)
            await query.answer("动作完成，按钮更新失败。", show_alert=True)
            return

    await query.answer()
