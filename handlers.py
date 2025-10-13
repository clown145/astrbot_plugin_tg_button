"""
为 tg_button 插件处理 Telegram 回调查询（Callback Query）逻辑。
"""
from __future__ import annotations
import asyncio
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

# 用于类型提示，防止循环导入
if TYPE_CHECKING:
    from .main import DynamicButtonFrameworkPlugin


async def handle_callback_query(plugin: "DynamicButtonFrameworkPlugin", update: Any, _context: Any) -> None:
    """处理回调查询的主入口点。"""
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
        elif data.startswith(plugin.CALLBACK_PREFIX_WORKFLOW):
            button_id = data[len(plugin.CALLBACK_PREFIX_WORKFLOW):]
            await handle_workflow_button(plugin, query, button_id)
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
    """处理动作按钮点击"""
    await _handle_executable_button(plugin, query, button_id, "action")


async def handle_workflow_button(plugin: "DynamicButtonFrameworkPlugin", query: Any, button_id: str) -> None:
    """处理工作流按钮点击"""
    await _handle_executable_button(plugin, query, button_id, "workflow")


async def _handle_executable_button(plugin: "DynamicButtonFrameworkPlugin", query: Any, button_id: str, button_type: str) -> None:
    """
    统一处理可执行按钮（动作和工作流）的核心逻辑。

    :param plugin: 插件实例。
    :param query: Telegram 回调查询对象。
    :param button_id: 被点击的按钮 ID。
    :param button_type: 按钮类型，'action' 或 'workflow'。
    """
    from .actions import RuntimeContext
    from .storage import ActionDefinition

    # --- 1. 数据获取和校验 ---
    snapshot = await plugin.button_store.get_snapshot()
    button = snapshot.buttons.get(button_id)
    if not button:
        await query.answer("按钮已不存在。", show_alert=True)
        return

    menu = plugin._find_menu_for_button(snapshot, button_id)
    if not menu:
        await query.answer("未找到按钮所属菜单。", show_alert=True)
        return

    message = query.message
    if not message:
        await query.answer("缺少消息上下文。", show_alert=True)
        return

    # --- 2. 准备要执行的动作 (Action) ---
    action_to_execute = None
    if button_type == "action":
        action_id = button.payload.get("action_id")
        if not action_id:
            await query.answer("未绑定动作。", show_alert=True)
            return
        action_to_execute = snapshot.actions.get(action_id)
        if not action_to_execute:
            await query.answer("动作不存在。", show_alert=True)
            return
    elif button_type == "workflow":
        workflow_id = button.payload.get("workflow_id")
        if not workflow_id:
            await query.answer("按钮未绑定工作流。", show_alert=True)
            return
        # 为工作流创建一个临时的 ActionDefinition 对象，以便 executor 能统一处理
        action_to_execute = ActionDefinition(
            id=f"workflow__{workflow_id}",
            name=f"Workflow: {workflow_id}",
            kind="workflow",
            config={"workflow_id": workflow_id},
        )

    if not action_to_execute:
        await query.answer("无法确定要执行的操作。", show_alert=True)
        return

    # --- 3. 创建运行时上下文 ---
    runtime = RuntimeContext(
        chat_id=str(message.chat.id),
        chat_type=message.chat.type,
        message_id=message.message_id,
        thread_id=getattr(message, "message_thread_id", None),
        user_id=str(query.from_user.id) if query.from_user else None,
        username=query.from_user.username if query.from_user else None,
        full_name=query.from_user.full_name if query.from_user else None,
        callback_data=query.data,
        variables={"menu_id": menu.id, "menu_name": menu.name},
    )

    # --- 4. 执行动作 ---
    result = await plugin.action_executor.execute(
        plugin,
        action_to_execute.to_dict(),
        button=button.to_dict(),
        menu=menu.to_dict(),
        runtime=runtime,
    )

    # --- 5. 处理执行结果 ---
    if not result.success:
        error_message = result.error or f"{button_type.capitalize()} 执行失败。"
        await query.answer(error_message, show_alert=True)
        return

    client = plugin._get_telegram_client()
    if not client:
        await query.answer("操作已执行，但无法更新消息。", show_alert=True)
        return

    # --- 5.1 计算最终的消息内容和按钮布局 ---
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

    # --- 5.2 根据结果更新消息或只显示通知 ---
    message_edited = False
    # 如果需要编辑消息文本，或者有新的文本内容
    if result.should_edit_message or result.new_text:
        if text_to_use != message.text or str(message.reply_markup) != str(reply_markup):
            try:
                await client.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    text=text_to_use,
                    reply_markup=reply_markup,
                    parse_mode=result.parse_mode,
                )
                message_edited = True
            except Exception as exc:
                plugin.logger.error(f"执行后更新消息失败: {exc}", exc_info=True)
                await query.answer("操作执行成功，但更新消息失败。", show_alert=True)
                return
    # 如果只需要更新按钮布局
    elif reply_markup and str(reply_markup) != str(message.reply_markup):
        try:
            await client.edit_message_reply_markup(
                chat_id=message.chat.id,
                message_id=message.message_id,
                reply_markup=reply_markup,
            )
            message_edited = True
        except Exception as exc:
            plugin.logger.error(f"更新按钮布局失败: {exc}", exc_info=True)
            await query.answer("操作完成，按钮更新失败。", show_alert=True)
            return

    # --- 5.3 显示通知或仅确认回调 ---
    if result.notification and result.notification.get("text"):
        await query.answer(**result.notification)
    elif not message_edited:
        # 如果消息没有被实际编辑，我们仍然需要应答回调以移除加载状态
        await query.answer()

