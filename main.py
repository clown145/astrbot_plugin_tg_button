import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType
from astrbot.api.message_components import Plain
from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
    from telegram.ext import Application, CallbackQueryHandler, ExtBot
except ImportError:  # pragma: no cover - optional dependency
    logger.error("Telegram 库未安装，请在 AstrBot 环境中执行 pip install python-telegram-bot")
    Application, CallbackQueryHandler, ExtBot, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo = (None,) * 6

try:  # 优先按包内路径导入，兼容旧版直接运行
    from .actions import ActionExecutor, RuntimeContext  # type: ignore
    from .storage import ButtonStore, ButtonsModel, ButtonDefinition, MenuDefinition, WebAppDefinition  # type: ignore
    from .webui import WebUIServer  # type: ignore
except ImportError:  # pragma: no cover - 兼容未打包场景
    from actions import ActionExecutor, RuntimeContext  # type: ignore
    from storage import ButtonStore, ButtonsModel, ButtonDefinition, MenuDefinition, WebAppDefinition  # type: ignore
    from webui import WebUIServer  # type: ignore

PLUGIN_NAME = "astrbot_plugin_tg_button"
BACK_BUTTON_TEXT = "返回"
CONFIG_PATH = Path(f"data/config/{PLUGIN_NAME}_config.json")
CONFIG_DEFAULTS: Dict[str, Any] = {
    "menu_command": "menu",
    "menu_header_text": "请选择功能",
    "webui_enabled": False,
    "webui_port": 17861,
    "webui_host": "127.0.0.1",
    "webui_exclusive": True,
    "webui_auth_token": "",
}


def get_plugin_data_path() -> Path:
    return StarTools.get_data_dir(PLUGIN_NAME)


def _load_raw_config() -> Dict[str, Any]:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as fp:
            return json.load(fp)
    except FileNotFoundError:
        logger.warning("按钮框架插件的配置文件未找到，将使用默认值。")
    except json.JSONDecodeError as exc:
        logger.error(f"解析配置文件 {CONFIG_PATH.name} 失败: {exc}，将使用默认值。")
    return {}


def _ensure_string(value: Any, default: str) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return default
    return str(value)


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_settings(raw: Dict[str, Any]) -> Dict[str, Any]:
    settings = dict(CONFIG_DEFAULTS)
    if raw:
        settings.update(raw)
    settings["menu_command"] = _ensure_string(settings.get("menu_command"), CONFIG_DEFAULTS["menu_command"])
    settings["menu_header_text"] = _ensure_string(settings.get("menu_header_text"), CONFIG_DEFAULTS["menu_header_text"])
    # 全局排列配置已取消，统一使用按钮的行/列布局
    settings["webui_enabled"] = _coerce_bool(raw.get("webui_enabled", settings["webui_enabled"]), CONFIG_DEFAULTS["webui_enabled"])
    settings["webui_port"] = _coerce_int(settings.get("webui_port"), CONFIG_DEFAULTS["webui_port"])
    settings["webui_host"] = _ensure_string(settings.get("webui_host"), CONFIG_DEFAULTS["webui_host"])
    settings["webui_exclusive"] = _coerce_bool(raw.get("webui_exclusive", settings["webui_exclusive"]), CONFIG_DEFAULTS["webui_exclusive"])
    settings["webui_auth_token"] = _ensure_string(settings.get("webui_auth_token"), CONFIG_DEFAULTS["webui_auth_token"])
    return settings


_INITIAL_SETTINGS = _build_settings(_load_raw_config())
MENU_COMMAND = _INITIAL_SETTINGS["menu_command"]


@register(
    PLUGIN_NAME,
    "clown145",
    "一个可以通过 Telegram 按钮与自定义 WebUI 管理的插件",
    "1.1.0",
    "https://github.com/clown145/astrbot_plugin_tg_button",
)
class DynamicButtonFrameworkPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.settings = _build_settings(_load_raw_config())
        self.menu_command = self.settings["menu_command"]
        self.menu_header = self.settings["menu_header_text"]
        # Layout is determined per button via row/column settings
        self.webui_enabled = self.settings["webui_enabled"]
        self.webui_exclusive = self.webui_enabled and self.settings["webui_exclusive"]
        self.button_store = ButtonStore(get_plugin_data_path(), logger=logger, default_header=self.menu_header)
        self.action_executor = ActionExecutor(logger=logger)
        self.webui_server: Optional[WebUIServer] = None
        self._callback_handler: Optional[CallbackQueryHandler] = None
        self._telegram_application: Optional[Any] = None
        self.CALLBACK_PREFIX_COMMAND = "tgbtn:cmd:"
        self.CALLBACK_PREFIX_MENU = "tgbtn:menu:"
        self.CALLBACK_PREFIX_BACK = "tgbtn:back:"
        self.CALLBACK_PREFIX_ACTION = "tgbtn:act:"
        logger.info(
            f"Dynamic button plugin loaded; menu command '/{self.menu_command}', WebUI={'enabled' if self.webui_enabled else 'disabled'}."
        )
        # 兼容热重载：初始化后尝试异步挂载回调与启动/停止 WebUI
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        try:
            loop.create_task(self._post_init_after_reload())
        except Exception:
            pass

    @filter.on_astrbot_loaded()
    async def _on_astrbot_loaded(self):
        await self._ensure_webui()
        await self._register_telegram_callbacks()

    async def _post_init_after_reload(self):
        # 给平台一点时间确保 application 就绪
        await asyncio.sleep(0.05)
        await self._ensure_webui()
        await self._register_telegram_callbacks()

    async def terminate(self):
        if self._callback_handler and self._telegram_application:
            try:
                self._telegram_application.remove_handler(self._callback_handler, group=1)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(f"移除 Telegram 回调处理器时出错: {exc}", exc_info=True)
            self._callback_handler = None
            self._telegram_application = None
        if self.webui_server:
            await self.webui_server.stop()
            self.webui_server = None
        await self.action_executor.close()

    async def _ensure_webui(self):
        if not self.webui_enabled:
            return
        if self.webui_server:
            return
        server = WebUIServer(
            logger=logger,
            data_store=self.button_store,
            action_executor=self.action_executor,
            host=self.settings["webui_host"],
            port=self.settings["webui_port"],
            auth_token=self.settings["webui_auth_token"],
        )
        if not server.is_supported:
            logger.error("未安装 aiohttp，无法启动 WebUI。")
            return
        self.webui_server = server
        try:
            await server.start()
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"启动 WebUI 失败: {exc}", exc_info=True)
            self.webui_server = None

    async def _register_telegram_callbacks(self):
        if self.webui_exclusive:
            logger.info("WebUI 独占模式开启，跳过 Telegram 回调注册。")
            return
        if not Application or not CallbackQueryHandler:
            logger.warning("python-telegram-bot 库不可用，无法注册回调。")
            return
        if self._callback_handler:
            return
        platform = self.context.get_platform("telegram")
        if not platform:
            logger.warning("未检测到 Telegram 平台，跳过回调注册。")
            return
        application = getattr(platform, "application", None)
        if not application:
            logger.error("无法注册回调处理器：platform 对象没有 application 属性。")
            return
        handler = CallbackQueryHandler(self._handle_callback_query)
        application.add_handler(handler, group=1)
        self._callback_handler = handler
        self._telegram_application = application
        logger.info("Telegram 动态按钮回调处理器已注册。")

    async def _handle_callback_query(self, update, _context):
        query = getattr(update, "callback_query", None)
        if not query or not query.data:
            return
        if self.webui_exclusive:
            await query.answer("WebUI 独占模式已启用，请通过 WebUI 操作。", show_alert=True)
            return
        data = query.data
        try:
            if data.startswith(self.CALLBACK_PREFIX_COMMAND):
                button_id = data[len(self.CALLBACK_PREFIX_COMMAND):]
                await self._handle_command_button(query, button_id)
            elif data.startswith(self.CALLBACK_PREFIX_MENU):
                menu_id = data[len(self.CALLBACK_PREFIX_MENU):] or "root"
                await self._handle_menu_navigation(query, menu_id)
            elif data.startswith(self.CALLBACK_PREFIX_BACK):
                menu_id = data[len(self.CALLBACK_PREFIX_BACK):] or "root"
                await self._handle_menu_navigation(query, menu_id)
            elif data.startswith(self.CALLBACK_PREFIX_ACTION):
                button_id = data[len(self.CALLBACK_PREFIX_ACTION):]
                await self._handle_action_button(query, button_id)
            else:
                await query.answer()
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"处理按钮回调时出错: {exc}", exc_info=True)
            await query.answer("处理失败，请稍后重试。", show_alert=True)

    async def _handle_command_button(self, query, button_id: str):
        snapshot = await self.button_store.get_snapshot()
        button = snapshot.buttons.get(button_id)
        if not button:
            await query.answer("按钮已不存在。", show_alert=True)
            return
        command_text = button.payload.get("command")
        if not command_text:
            await query.answer("按钮未绑定指令。", show_alert=True)
            return
        await query.answer()
        await self._dispatch_command(query, command_text)

    async def _handle_menu_navigation(self, query, target_menu_id: str):
        snapshot = await self.button_store.get_snapshot()
        markup, header = self._build_menu_markup(target_menu_id or "root", snapshot)
        if not markup:
            await query.answer("目标菜单不存在。", show_alert=True)
            return
        client = self._get_telegram_client()
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
                text=header or self.menu_header,
                reply_markup=markup,
            )
        except Exception as exc:
            logger.error(f"切换菜单时出错: {exc}", exc_info=True)
            await query.answer("切换失败，请稍后再试。", show_alert=True)
            return
        await query.answer()

    async def _handle_action_button(self, query, button_id: str):
        snapshot = await self.button_store.get_snapshot()
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
        menu = self._find_menu_for_button(snapshot, button_id)
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
                "replied_text": replied_text or replied_caption
            },
        )
        result = await self.action_executor.execute(
            action.to_dict(),
            button=button.to_dict(),
            menu=menu.to_dict(),
            runtime=runtime,
        )
        if not result.success:
            await query.answer(result.error or "动作执行失败。", show_alert=True)
            return
        client = self._get_telegram_client()
        if not client:
            await query.answer("动作已执行，但无法更新消息。", show_alert=True)
            return
        target_menu_id = result.next_menu_id or menu.id
        next_snapshot = await self.button_store.get_snapshot()
        overrides_map: Dict[str, Dict[str, Any]] = {}
        if result.button_overrides:
            overrides_map = self._resolve_button_overrides(next_snapshot, menu, result.button_overrides, button_id)
        if result.button_title:
            overrides_map.setdefault(button_id, {}).setdefault('text', result.button_title)
        markup, header = self._build_menu_markup(target_menu_id, next_snapshot, overrides=overrides_map)
        reply_markup = markup if markup else None
        text_to_use = result.new_text or header or getattr(message, "text", self.menu_header)
        if result.should_edit_message or result.new_text:
            try:
                await client.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    text=text_to_use,
                    reply_markup=reply_markup,
                    parse_mode=result.parse_mode,
                )
            except Exception as exc:
                logger.error(f"执行动作后更新消息失败: {exc}", exc_info=True)
                await query.answer("动作执行成功，但更新消息失败。", show_alert=True)
                return
        elif reply_markup:
            try:
                await client.edit_message_reply_markup(
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    reply_markup=reply_markup,
                )
            except Exception as exc:
                logger.error(f"更新按钮布局失败: {exc}", exc_info=True)
                await query.answer("动作完成，按钮更新失败。", show_alert=True)
                return
        await query.answer()

    async def _dispatch_command(self, query, command_text: str):
        platform = self.context.get_platform("telegram")
        if not platform:
            logger.warning("未找到 Telegram 平台，无法转发指令。")
            return
        client = self._get_telegram_client()
        if not client:
            return
        message = query.message
        if not message:
            return
        fake_message = AstrBotMessage()
        is_private = message.chat.type == "private"
        chat_id = str(message.chat.id)
        thread_id = getattr(message, "message_thread_id", None)
        if is_private:
            fake_message.type = MessageType.FRIEND_MESSAGE
            fake_message.group_id = ""
            fake_message.session_id = chat_id
        else:
            fake_message.type = MessageType.GROUP_MESSAGE
            session_id = f"{chat_id}#{thread_id}" if thread_id is not None else chat_id
            fake_message.group_id = session_id
            fake_message.session_id = session_id
        fake_message.self_id = str(getattr(client, "id", ""))
        fake_message.message_id = f"{message.message_id}_btn"
        sender = message.from_user
        fake_message.sender = MessageMember(
            user_id=str(sender.id) if sender else "unknown",
            nickname=(sender.full_name if sender else None) or (sender.username if sender else "Unknown"),
        )
        fake_message.message_str = command_text
        fake_message.raw_message = query
        fake_message.timestamp = int(message.date.timestamp()) if message.date else 0
        fake_message.message = [Plain(command_text)]
        fake_event = TelegramPlatformEvent(
            message_str=command_text,
            message_obj=fake_message,
            platform_meta=platform.meta(),
            session_id=fake_message.session_id,
            client=client,
        )
        fake_event.context = self.context
        fake_event.is_at_or_wake_command = True
        self.context.get_event_queue().put_nowait(fake_event)

    def _get_telegram_client(self) -> Optional[ExtBot]:
        platform = self.context.get_platform("telegram")
        if not platform:
            return None
        try:
            return platform.get_client()
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"获取 Telegram 客户端失败: {exc}", exc_info=True)
            return None

    def _build_menu_markup(
            self,
            menu_id: str,
            snapshot: ButtonsModel,
            overrides: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Tuple[Optional[InlineKeyboardMarkup], Optional[str]]:
        if not InlineKeyboardMarkup or not InlineKeyboardButton:
            return None, None
        menu = snapshot.menus.get(menu_id)
        if not menu:
            return None, None
        button_entities: List[ButtonDefinition] = [
            snapshot.buttons.get(btn_id) for btn_id in menu.items if snapshot.buttons.get(btn_id)
        ]
        overrides = overrides or {}
        rows: List[List[InlineKeyboardButton]] = []
        if self._should_stack(button_entities, menu, overrides):
            for btn in button_entities:
                override = overrides.get(btn.id)
                widget = self._create_inline_button(btn, snapshot, override)
                if widget:
                    rows.append([widget])
        else:
            row_map: Dict[int, List[Tuple[int, InlineKeyboardButton]]] = {}

            def add_widget(row_index: int, col_index: int, widget: InlineKeyboardButton) -> None:
                row_map.setdefault(row_index, []).append((col_index, widget))

            for btn in button_entities:
                override = overrides.get(btn.id)
                widget = self._create_inline_button(btn, snapshot, override)
                if not widget:
                    continue
                layout_override = override.get('layout') if override else None
                layout_row = layout_override.get('row') if layout_override and 'row' in layout_override else btn.layout.row
                layout_col = layout_override.get('col') if layout_override and 'col' in layout_override else btn.layout.col
                add_widget(layout_row, layout_col, widget)

            for row_idx in sorted(row_map.keys()):
                ordered = [widget for _, widget in sorted(row_map[row_idx], key=lambda item: item[0])]
                if ordered:
                    rows.append(ordered)
        if not rows:
            return None, menu.header or self.menu_header
        return InlineKeyboardMarkup(rows), menu.header or self.menu_header
    def _should_stack(
        self,
        buttons: List[ButtonDefinition],
        menu: MenuDefinition,
        overrides: Dict[str, Dict[str, Any]],
    ) -> bool:
        if not buttons:
            return False
        for btn in buttons:
            if btn.layout.row != 0 or btn.layout.col != 0:
                return False
            if btn.layout.rowspan != 1 or btn.layout.colspan != 1:
                return False
            override = overrides.get(btn.id)
            if override and override.get('layout'):
                return False
        return True

    def _resolve_web_app_url(self, web_app: WebAppDefinition) -> Optional[str]:
        if web_app.kind == 'external':
            return web_app.url
        return web_app.url or ''
    def _resolve_button_overrides(
        self,
        snapshot: ButtonsModel,
        menu: MenuDefinition,
        overrides: List[Dict[str, Any]],
        current_button_id: str,
    ) -> Dict[str, Dict[str, Any]]:
        resolved: Dict[str, Dict[str, Any]] = {}
        for entry in overrides or []:
            if not isinstance(entry, dict):
                continue
            target = entry.get('target', 'self')
            base = {k: v for k, v in entry.items() if k != 'target'}
            if not base:
                continue
            target_ids = self._resolve_override_targets(snapshot, menu, target, current_button_id)
            for button_id in target_ids:
                bucket = resolved.setdefault(button_id, {})
                bucket.update(base)
        return resolved

    def _resolve_override_targets(
        self,
        snapshot: ButtonsModel,
        menu: MenuDefinition,
        target: str,
        current_button_id: str,
    ) -> List[str]:
        if not target:
            target = 'self'
        lowered = target.lower()
        if lowered == 'self':
            return [current_button_id] if current_button_id in snapshot.buttons else []
        if lowered.startswith('id:'):
            candidate = target.split(':', 1)[1]
            return [candidate] if candidate in snapshot.buttons else []
        if lowered.startswith('button:'):
            candidate = target.split(':', 1)[1]
            return [candidate] if candidate in snapshot.buttons else []
        if lowered.startswith('index:'):
            try:
                idx = int(target.split(':', 1)[1])
                if 0 <= idx < len(menu.items):
                    candidate = menu.items[idx]
                    return [candidate] if candidate in snapshot.buttons else []
            except Exception:
                return []
        if target in snapshot.buttons:
            return [target]
        return []
    def _create_inline_button(
        self,
        button: ButtonDefinition,
        snapshot: ButtonsModel,
        override: Optional[Dict[str, Any]] = None,
    ) -> Optional[InlineKeyboardButton]:
        if not InlineKeyboardButton:
            return None
        override = override or {}
        text = override.get('text') or button.text or '未命名'
        if override.get('switch_inline_query') or override.get('switch_inline_query_current_chat'):
            return InlineKeyboardButton(
                text,
                switch_inline_query=override.get('switch_inline_query'),
                switch_inline_query_current_chat=override.get('switch_inline_query_current_chat'),
            )
        raw_callback = override.get('raw_callback_data')
        if raw_callback:
            return InlineKeyboardButton(text, callback_data=raw_callback)
        btn_type = (override.get('type') or button.type or 'command').lower()
        if btn_type == 'raw':
            callback_data = override.get('callback_data')
            if not callback_data:
                return None
            return InlineKeyboardButton(text, callback_data=callback_data)
        if btn_type == 'command':
            if not button.payload.get('command'):
                return None
            return InlineKeyboardButton(text, callback_data=f"{self.CALLBACK_PREFIX_COMMAND}{button.id}")
        if btn_type == 'url':
            url = override.get('url') or button.payload.get('url')
            if not url:
                return None
            return InlineKeyboardButton(text, url=url)
        if btn_type == 'submenu':
            target = override.get('menu_id') or button.payload.get('menu_id')
            if not target:
                return None
            return InlineKeyboardButton(text, callback_data=f"{self.CALLBACK_PREFIX_MENU}{target}")
        if btn_type == 'action':
            override_action = override.get('action_id')
            if override_action:
                button.payload = dict(button.payload)
                button.payload['action_id'] = override_action
            if not button.payload.get('action_id'):
                return None
            return InlineKeyboardButton(text, callback_data=f"{self.CALLBACK_PREFIX_ACTION}{button.id}")
        if btn_type == 'inline_query':
            query_text = override.get('query') or button.payload.get('query', '')
            return InlineKeyboardButton(text, switch_inline_query_current_chat=query_text)
        if btn_type == 'web_app':
            web_app_id = override.get('web_app_id') or button.payload.get('web_app_id')
            url = override.get('web_app_url') or override.get('url') or button.payload.get('url')
            if web_app_id:
                web_app = snapshot.web_apps.get(web_app_id)
                if web_app:
                    resolved = self._resolve_web_app_url(web_app)
                    if resolved:
                        url = resolved
            if not url or not WebAppInfo:
                return None
            return InlineKeyboardButton(text, web_app=WebAppInfo(url=url))
        if btn_type == 'back':
            target = override.get('menu_id') or button.payload.get('menu_id') or button.payload.get('target_menu')
            if not target:
                return None
            return InlineKeyboardButton(text, callback_data=f"{self.CALLBACK_PREFIX_BACK}{target}")
        return None
    def _find_menu_for_button(self, snapshot: ButtonsModel, button_id: str) -> Optional[MenuDefinition]:
        for menu in snapshot.menus.values():
            if button_id in menu.items:
                return menu
        return None

    def _split_chat_id(self, chat_id_str: str) -> Tuple[str, Optional[int]]:
        if "#" in chat_id_str:
            chat, _, thread = chat_id_str.partition("#")
            try:
                return chat, int(thread)
            except ValueError:
                return chat, None
        return chat_id_str, None

    @filter.command(MENU_COMMAND)
    async def send_menu(self, event: AstrMessageEvent):
        if self.webui_exclusive:
            yield event.plain_result("WebUI 独占模式已启用，请通过 WebUI 操作按钮。")
            return
        if event.get_platform_name() != "telegram":
            yield event.plain_result("当前仅支持 Telegram 平台。")
            return
        if not InlineKeyboardMarkup or not InlineKeyboardButton:
            yield event.plain_result("python-telegram-bot 库不可用，无法发送菜单。")
            return
        snapshot = await self.button_store.get_snapshot()
        markup, header = self._build_menu_markup("root", snapshot)
        if not markup:
            yield event.plain_result("当前未配置任何按钮。")
            return
        client = self._get_telegram_client()
        if not client:
            yield event.plain_result("无法获取 Telegram 客户端，请检查日志。")
            return
        chat_id_str = event.get_group_id() or event.get_sender_id()
        if not chat_id_str:
            yield event.plain_result("无法确定会话上下文。")
            return
        chat_id, thread_id = self._split_chat_id(chat_id_str)
        try:
            await client.send_message(
                chat_id=chat_id,
                text=header or self.menu_header,
                reply_markup=markup,
                message_thread_id=thread_id,
            )
        except Exception as exc:
            logger.error(f"发送自定义菜单失败: {exc}", exc_info=True)
            yield event.plain_result("发送菜单时出错，请查看后台日志。")
            return
        event.stop_event()

    @filter.command("bind", alias={"绑定"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def bind_button(self, event: AstrMessageEvent):
        if self.webui_exclusive:
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
        await self.button_store.upsert_simple_button(text, btn_type, value)
        yield event.plain_result(f"按钮 '{text}' 已成功绑定为 {btn_type}。")

    @filter.command("unbind", alias={"解绑"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def unbind_button(self, event: AstrMessageEvent):
        if self.webui_exclusive:
            yield event.plain_result("WebUI 独占模式已启用，请在 WebUI 中管理按钮。")
            return
        args = event.message_str.strip().split()
        if len(args) < 2:
            yield event.plain_result("请输入要解绑的按钮文本。")
            return
        text = " ".join(args[1:])
        removed = await self.button_store.remove_button_by_text(text)
        if removed:
            yield event.plain_result(f"按钮 '{text}' 已成功解绑。")
        else:
            yield event.plain_result(f"未找到名为 '{text}' 的按钮。")