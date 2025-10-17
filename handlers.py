"""
为 tg_button 插件处理 Telegram 回调查询（Callback Query）逻辑。
"""

from __future__ import annotations
import asyncio
import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import aiofiles
import aiofiles.os

from astrbot.api.event import MessageChain
import astrbot.api.message_components as Comp

# 用于类型提示，防止循环导入
if TYPE_CHECKING:
    from .main import DynamicButtonFrameworkPlugin


async def handle_callback_query(
    plugin: "DynamicButtonFrameworkPlugin", update: Any, _context: Any
) -> None:
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
            button_id = data[len(plugin.CALLBACK_PREFIX_COMMAND) :]
            await handle_command_button(plugin, query, button_id)
        elif data.startswith(plugin.CALLBACK_PREFIX_REDIRECT):
            await handle_redirect_callback(plugin, query, data)
        elif data.startswith(plugin.CALLBACK_PREFIX_MENU):
            menu_id = data[len(plugin.CALLBACK_PREFIX_MENU) :] or "root"
            await handle_menu_navigation(plugin, query, menu_id)
        elif data.startswith(plugin.CALLBACK_PREFIX_BACK):
            menu_id = data[len(plugin.CALLBACK_PREFIX_BACK) :] or "root"
            await handle_menu_navigation(plugin, query, menu_id)
        elif data.startswith(plugin.CALLBACK_PREFIX_ACTION):
            button_id = data[len(plugin.CALLBACK_PREFIX_ACTION) :]
            await handle_action_button(plugin, query, button_id)
        elif data.startswith(plugin.CALLBACK_PREFIX_WORKFLOW):
            button_id = data[len(plugin.CALLBACK_PREFIX_WORKFLOW) :]
            await handle_workflow_button(plugin, query, button_id)
        else:
            await query.answer()
    except Exception as exc:
        plugin.logger.error(f"处理按钮回调时出错: {exc}", exc_info=True)
        await query.answer("处理失败，请稍后重试。", show_alert=True)


async def handle_command_button(
    plugin: "DynamicButtonFrameworkPlugin", query: Any, button_id: str
) -> None:
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


async def handle_redirect_callback(
    plugin: "DynamicButtonFrameworkPlugin", query: Any, data: str
) -> None:
    payload = data[len(plugin.CALLBACK_PREFIX_REDIRECT) :]
    if not payload:
        await query.answer("重定向数据缺失。", show_alert=True)
        return

    origin_id, target_id, focus_flag = (payload.split(":", 2) + ["0"] * 3)[:3]
    origin_id = origin_id or ""
    target_id = target_id or ""
    focus_target_menu = focus_flag == "1"

    if not target_id:
        await query.answer("重定向目标无效。", show_alert=True)
        return

    snapshot = await plugin.button_store.get_snapshot()
    target_button = snapshot.buttons.get(target_id)
    if not target_button:
        await query.answer("目标按钮已不存在。", show_alert=True)
        return

    origin_button_id = origin_id or target_button.id
    origin_menu = plugin._find_menu_for_button(snapshot, origin_button_id)
    origin_menu_id = origin_menu.id if origin_menu else None

    btn_type = (target_button.type or "command").lower()

    if btn_type == "command":
        await handle_command_button(plugin, query, target_button.id)
        return

    if btn_type == "submenu":
        menu_id = target_button.payload.get("menu_id")
        if not menu_id:
            await query.answer("目标菜单不存在。", show_alert=True)
            return
        await handle_menu_navigation(plugin, query, menu_id)
        return

    if btn_type == "back":
        menu_id = target_button.payload.get("menu_id") or target_button.payload.get(
            "target_menu"
        )
        if not menu_id:
            await query.answer("返回目标缺失。", show_alert=True)
            return
        await handle_menu_navigation(plugin, query, menu_id)
        return

    if btn_type == "action":
        await _handle_executable_button(
            plugin,
            query,
            target_button.id,
            "action",
            origin_button_id=origin_button_id,
            origin_menu_id=origin_menu_id,
            focus_target_menu=focus_target_menu,
        )
        return

    if btn_type == "workflow":
        await _handle_executable_button(
            plugin,
            query,
            target_button.id,
            "workflow",
            origin_button_id=origin_button_id,
            origin_menu_id=origin_menu_id,
            focus_target_menu=focus_target_menu,
        )
        return

    await query.answer("暂不支持该重定向目标类型。", show_alert=True)


async def handle_menu_navigation(
    plugin: "DynamicButtonFrameworkPlugin", query: Any, target_menu_id: str
) -> None:
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


async def _prepare_execution_context(
    plugin: "DynamicButtonFrameworkPlugin",
    query: Any,
    button_id: str,
    button_type: str,
    *,
    origin_button_id: Optional[str] = None,
    origin_menu_id: Optional[str] = None,
    focus_target_menu: bool = False,
) -> Optional[Tuple[Any, Any, Any, Any, Any, Optional[str], str]]:
    """获取并校验执行动作所需的所有上下文。如果校验失败，返回 None 并应答查询。"""
    from .actions import RuntimeContext
    from .storage import ActionDefinition

    snapshot = await plugin.button_store.get_snapshot()
    button = snapshot.buttons.get(button_id)
    if not button:
        await query.answer("按钮已不存在。", show_alert=True)
        return None

    menu = plugin._find_menu_for_button(snapshot, button_id)
    if not menu:
        await query.answer("未找到按钮所属菜单。", show_alert=True)
        return None

    message = query.message
    if not message:
        await query.answer("缺少消息上下文。", show_alert=True)
        return None

    resolved_origin_button_id = origin_button_id or button.id
    origin_button = snapshot.buttons.get(resolved_origin_button_id)

    resolved_origin_menu = None
    if origin_menu_id:
        resolved_origin_menu = snapshot.menus.get(origin_menu_id)
    if not resolved_origin_menu and resolved_origin_button_id:
        resolved_origin_menu = plugin._find_menu_for_button(
            snapshot, resolved_origin_button_id
        )
    resolved_origin_menu_id = (
        resolved_origin_menu.id if resolved_origin_menu else menu.id
    )

    action_to_execute = None
    if button_type == "action":
        action_id = button.payload.get("action_id")
        if not action_id:
            await query.answer("未绑定动作。", show_alert=True)
            return None
        action_to_execute = snapshot.actions.get(action_id)
        if not action_to_execute:
            await query.answer("动作不存在。", show_alert=True)
            return None
    elif button_type == "workflow":
        workflow_id = button.payload.get("workflow_id")
        if not workflow_id:
            await query.answer("按钮未绑定工作流。", show_alert=True)
            return None
        action_to_execute = ActionDefinition(
            id=f"workflow__{workflow_id}",
            name=f"Workflow: {workflow_id}",
            kind="workflow",
            config={"workflow_id": workflow_id},
        )

    if not action_to_execute:
        await query.answer("无法确定要执行的操作。", show_alert=True)
        return None

    runtime_variables = {
        "menu_id": menu.id,
        "menu_name": menu.name,
        "button_id": button.id,
        "button_text": button.text,
        "menu_header_text": getattr(message, "text", None),
        "origin_button_id": resolved_origin_button_id,
        "origin_button_text": getattr(origin_button, "text", None),
        "origin_menu_id": resolved_origin_menu_id,
        "origin_menu_name": getattr(resolved_origin_menu, "name", None)
        or menu.name,
        "redirect_origin_button_id": resolved_origin_button_id,
        "redirect_origin_menu_id": resolved_origin_menu_id,
        "redirect_target_button_id": button.id,
        "redirect_target_menu_id": menu.id,
        "redirect_focus_target_menu": focus_target_menu,
    }

    runtime = RuntimeContext(
        chat_id=str(message.chat.id),
        chat_type=message.chat.type,
        message_id=message.message_id,
        thread_id=getattr(message, "message_thread_id", None),
        user_id=str(query.from_user.id) if query.from_user else None,
        username=query.from_user.username if query.from_user else None,
        full_name=query.from_user.full_name if query.from_user else None,
        callback_data=query.data,
        variables=runtime_variables,
    )

    return (
        button,
        menu,
        message,
        runtime,
        action_to_execute,
        resolved_origin_menu_id,
        resolved_origin_button_id,
    )


async def handle_action_button(
    plugin: "DynamicButtonFrameworkPlugin", query: Any, button_id: str
) -> None:
    """处理动作按钮点击"""
    await _handle_executable_button(plugin, query, button_id, "action")


async def handle_workflow_button(
    plugin: "DynamicButtonFrameworkPlugin", query: Any, button_id: str
) -> None:
    """处理工作流按钮点击"""
    await _handle_executable_button(plugin, query, button_id, "workflow")


async def _handle_executable_button(
    plugin: "DynamicButtonFrameworkPlugin",
    query: Any,
    button_id: str,
    button_type: str,
    *,
    origin_button_id: Optional[str] = None,
    origin_menu_id: Optional[str] = None,
    focus_target_menu: bool = False,
) -> None:
    """
    统一处理可执行按钮（动作和工作流）的核心逻辑。
    通过立即响应查询并将实际工作放入后台任务，避免阻塞 Telegram 的更新循环。
    """
    context = await _prepare_execution_context(
        plugin,
        query,
        button_id,
        button_type,
        origin_button_id=origin_button_id,
        origin_menu_id=origin_menu_id,
        focus_target_menu=focus_target_menu,
    )
    if not context:
        return

    async def execute_and_process():
        """在后台执行动作并处理其结果。"""
        (
            button,
            menu,
            message,
            runtime,
            action_to_execute,
            resolved_origin_menu_id,
            resolved_origin_button_id,
        ) = context
        try:
            result = await plugin.action_executor.execute(
                plugin,
                action_to_execute.to_dict(),
                button=button.to_dict(),
                menu=menu.to_dict(),
                runtime=runtime,
            )
            # 注意：此处的 `query` 可能已超时，`query.answer()` 调用会失败。
            # 这是一个已知的副作用，如果需要完美的通知，需要进一步改造 _process_execution_result。
            await _process_execution_result(
                plugin,
                query,
                result,
                message,
                menu,
                resolved_origin_button_id,
                button_type,
                runtime,
                origin_menu_id=resolved_origin_menu_id,
            )
        except Exception as e:
            plugin.logger.error(
                f"后台任务执行失败 (button_id: {button_id}): {e}", exc_info=True
            )
            # 尝试发送一个新消息来通知用户错误
            try:
                client = plugin._get_telegram_client()
                if client and runtime:
                    await client.send_message(
                        chat_id=runtime.chat_id,
                        text=f"执行“{button.name}”时发生后台错误。",
                    )
            except Exception as inner_exc:
                plugin.logger.error(f"无法发送后台错误通知: {inner_exc}")

    # 将耗时的操作调度为后台任务，后台任务将负责响应回调
    asyncio.create_task(execute_and_process())


async def _process_execution_result(
    plugin: "DynamicButtonFrameworkPlugin",
    query: Any,
    result: Any,
    message: Any,
    menu: Any,
    current_button_id: str,
    button_type: str,
    runtime: Any,
    *,
    origin_menu_id: Optional[str] = None,
) -> None:
    """处理动作和工作流的执行结果。"""
    try:
        # --- Handle sending a new message chain (e.g., from send_message action) ---
        if result.new_message_chain and isinstance(result.new_message_chain, list):
            client = plugin._get_telegram_client()
            if not client:
                plugin.logger.warning("无法获取 Telegram 客户端以发送新消息。")
                return

            def is_local_path(source: Any) -> bool:
                s = str(source)
                return s.startswith("/") or ":\\" in s

            try:
                text_parts, image_source, voice_source = [], None, None
                for comp_data in result.new_message_chain:
                    comp_type = comp_data.get("type", "").lower()
                    if comp_type == "plain":
                        text_parts.append(comp_data.get("text", ""))
                    elif comp_type == "image":
                        image_source = comp_data.get("source")
                    elif comp_type == "voice":
                        voice_source = comp_data.get("source")
                caption = "\n".join(text_parts)

                if image_source:
                    if is_local_path(image_source):
                        async with aiofiles.open(image_source, "rb") as f:
                            await client.send_photo(
                                chat_id=runtime.chat_id, photo=f, caption=caption
                            )
                    else:
                        await client.send_photo(
                            chat_id=runtime.chat_id, photo=image_source, caption=caption
                        )
                elif voice_source:
                    if is_local_path(voice_source):
                        async with aiofiles.open(voice_source, "rb") as f:
                            await client.send_voice(
                                chat_id=runtime.chat_id, voice=f, caption=caption
                            )
                    else:
                        await client.send_voice(
                            chat_id=runtime.chat_id, voice=voice_source, caption=caption
                        )
                elif caption:
                    await client.send_message(chat_id=runtime.chat_id, text=caption)
            except Exception as exc:
                plugin.logger.error(f"后台发送新消息失败: {exc}", exc_info=True)
            return  # A new message chain is a terminal action for the original message.

        # --- Handle failures ---
        if not result.success:
            error_message = result.error or f"{button_type.capitalize()} 执行失败。"
            if len(error_message) > 200:
                error_message = error_message[:197] + "..."
            try:
                await query.answer(error_message, show_alert=True)
            except Exception as e:
                plugin.logger.warning(f"无法在后台显示错误弹窗: {e}")
            return

        # --- Handle successful result: update original message or show notification ---
        client = plugin._get_telegram_client()
        if not client:
            plugin.logger.warning("无法获取 Telegram 客户端以更新消息。")
            return

        origin_menu_fallback = (
            origin_menu_id
            or runtime.variables.get("redirect_origin_menu_id")
            or runtime.variables.get("origin_menu_id")
            or menu.id
        )
        target_menu_id = origin_menu_fallback
        if result.next_menu_id:
            target_menu_id = result.next_menu_id
        else:
            focus_target_menu = bool(
                runtime.variables.get("redirect_focus_target_menu")
            )
            forced_menu = runtime.variables.get("redirect_target_menu_id")
            if focus_target_menu and forced_menu:
                target_menu_id = forced_menu
        next_snapshot = await plugin.button_store.get_snapshot()
        overrides_map: Dict[str, Dict[str, Any]] = {}
        if result.button_overrides:
            overrides_map = plugin._resolve_button_overrides(
                next_snapshot, menu, result.button_overrides, current_button_id
            )
        if result.button_title:
            overrides_map.setdefault(current_button_id, {}).setdefault(
                "text", result.button_title
            )

        markup, header = plugin._build_menu_markup(
            target_menu_id, next_snapshot, overrides=overrides_map
        )
        reply_markup = markup if markup else None
        text_to_use = (
            result.new_text or header or getattr(message, "text", plugin.menu_header)
        )

        message_edited = False
        # Only edit if there's an actual change in text or markup
        if (result.should_edit_message or result.new_text) and (
            text_to_use != message.text
            or str(message.reply_markup) != str(reply_markup)
        ):
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
        # Fallback to only editing markup if text is same but markup changed
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

        # --- Finally, answer the query ---
        # This is the single point where we interact with the original query.
        try:
            if result.notification and result.notification.get("text"):
                # If a specific notification is requested, show it. This is highest priority.
                await query.answer(**result.notification)
            elif not message_edited:
                # If nothing visual happened (no message edit), answer the query to stop the loading animation.
                await query.answer()
        except Exception as e:
            # It's possible the query timed out, which is okay. Log it for debugging.
            plugin.logger.info(f"在后台响应回调查询时出错 (可能已超时): {e}")

    finally:
        if result and result.temp_files_to_clean:
            plugin.logger.info(
                f"处理完动作后开始清理临时文件: {result.temp_files_to_clean}"
            )
            for file_path in result.temp_files_to_clean:
                try:
                    if file_path and await aiofiles.os.path.exists(file_path):
                        await aiofiles.os.remove(file_path)
                        plugin.logger.info(f"  -> 已删除临时文件: {file_path}")
                except Exception as exc:
                    plugin.logger.error(f"  -> 清理临时文件 {file_path} 失败: {exc}")
