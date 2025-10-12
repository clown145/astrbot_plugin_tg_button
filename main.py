"""
Main plugin file for the AstrBot Telegram Button Framework.
This file contains the core plugin class, lifecycle management, and registers handlers
which delegate the actual logic to other modules.
"""

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType
from astrbot.api.message_components import Plain
from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent

# --- Telegram-specific imports with fallback ---
try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
    from telegram.ext import Application, CallbackQueryHandler, ExtBot
except ImportError:  # pragma: no cover - optional dependency
    logger.error("Telegram 库未安装，请在 AstrBot 环境中执行 pip install python-telegram-bot")
    Application, CallbackQueryHandler, ExtBot, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo = (None,) * 6

# --- Local module imports ---

# Import the command name for the decorator BEFORE the class is defined
from .config import MENU_COMMAND, PLUGIN_NAME, build_settings

# Import logic handlers
from . import commands
from . import handlers
from .actions import ActionExecutor
from .storage import ButtonStore, ButtonsModel, ButtonDefinition, MenuDefinition, WebAppDefinition
from .webui import WebUIServer

BACK_BUTTON_TEXT = "返回"

def get_plugin_data_path() -> Path:
    return StarTools.get_data_dir(PLUGIN_NAME)


@register(
    PLUGIN_NAME,
    "clown145",
    "一个可以通过 Telegram 按钮与自定义 WebUI 管理的插件",
    "1.1.2",
    "https://github.com/clown145/astrbot_plugin_tg_button",
)
class DynamicButtonFrameworkPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        # Build settings using the function from the config module
        self.settings = build_settings(config)
        self.logger = logger

        # Core plugin components
        self.menu_command = self.settings["menu_command"]
        self.menu_header = self.settings["menu_header_text"]
        self.webui_enabled = self.settings["webui_enabled"]
        self.webui_exclusive = self.webui_enabled and self.settings["webui_exclusive"]
        self.button_store = ButtonStore(get_plugin_data_path(), logger=logger, default_header=self.menu_header)
        self.action_executor = ActionExecutor(logger=logger)
        self.webui_server: Optional[WebUIServer] = None

        # Telegram-specific state
        self._callback_handler: Optional[CallbackQueryHandler] = None
        self._telegram_application: Optional[Any] = None

        # Callback prefixes used by handlers
        self.CALLBACK_PREFIX_COMMAND = "tgbtn:cmd:"
        self.CALLBACK_PREFIX_MENU = "tgbtn:menu:"
        self.CALLBACK_PREFIX_BACK = "tgbtn:back:"
        self.CALLBACK_PREFIX_ACTION = "tgbtn:act:"

        logger.info(
            f"Dynamic button plugin loaded; menu command '/{self.menu_command}', WebUI={'enabled' if self.webui_enabled else 'disabled'}."
        )

        # Handle hot-reloading
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        loop.create_task(self._post_init_after_reload())

    # --- Plugin Lifecycle Management ---

    @filter.on_astrbot_loaded()
    async def _on_astrbot_loaded(self):
        await self._ensure_webui()
        await self._register_telegram_callbacks()

    async def _post_init_after_reload(self):
        await asyncio.sleep(0.05)
        await self._ensure_webui()
        await self._register_telegram_callbacks()

    async def terminate(self):
        if self._callback_handler and self._telegram_application:
            try:
                self._telegram_application.remove_handler(self._callback_handler, group=1)
            except Exception as exc:
                logger.error(f"移除 Telegram 回调处理器时出错: {exc}", exc_info=True)
            self._callback_handler = None
            self._telegram_application = None
        if self.webui_server:
            await self.webui_server.stop()
            self.webui_server = None
        await self.action_executor.close()

    # --- Internal Setup ---

    async def _ensure_webui(self):
        if not self.webui_enabled or self.webui_server:
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
        except Exception as exc:
            logger.error(f"启动 WebUI 失败: {exc}", exc_info=True)
            self.webui_server = None

    async def _register_telegram_callbacks(self):
        if self.webui_exclusive:
            logger.info("WebUI 独占模式开启，跳过 Telegram 回调注册。")
            return
        if not Application or not CallbackQueryHandler or self._callback_handler:
            return

        platform = self.context.get_platform("telegram")
        if not platform:
            logger.warning("未检测到 Telegram 平台，跳过回调注册。")
            return

        application = getattr(platform, "application", None)
        if not application:
            logger.error("无法注册回调处理器：platform 对象没有 application 属性。")
            return

        # The handler function is now a wrapper that calls the logic in handlers.py
        handler = CallbackQueryHandler(self._handle_callback_query)
        application.add_handler(handler, group=1)
        self._callback_handler = handler
        self._telegram_application = application
        logger.info("Telegram 动态按钮回调处理器已注册。")

    # --- Event Handlers (Wrappers) ---

    def _handle_callback_query(self, update, _context):
        """Wrapper to delegate callback query handling to the handlers module."""
        handlers.async_handle_callback_query(self, update, _context)

    @filter.command(MENU_COMMAND)
    async def send_menu(self, event: AstrMessageEvent):
        """显示可交互的按钮菜单"""
        async for result in commands.send_menu(self, event):
            yield result

    @filter.command("bind", alias={"绑定"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def bind_button(self, event: AstrMessageEvent):
        """绑定一个新的按钮"""
        async for result in commands.bind_button(self, event):
            yield result

    @filter.command("unbind", alias={"解绑"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def unbind_button(self, event: AstrMessageEvent):
        """解绑一个已有的按钮"""
        async for result in commands.unbind_button(self, event):
            yield result

    # --- Internal Helper & Service Methods ---
    # These methods remain in the main class because they are used by the
    # external handlers and commands via the 'plugin' instance.

    async def _dispatch_command(self, query, command_text: str):
        platform = self.context.get_platform("telegram")
        if not platform or not (client := self._get_telegram_client()) or not (message := query.message):
            return

        fake_message = AstrBotMessage()
        is_private = message.chat.type == "private"
        chat_id = str(message.chat.id)
        thread_id = getattr(message, "message_thread_id", None)

        if is_private:
            fake_message.type = MessageType.FRIEND_MESSAGE
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
        except Exception as exc:
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
            callback_data = override.get('callback_data') or button.payload.get('callback_data')
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
        if btn_type == 'switch_inline_query':
            query_text = override.get('query') or button.payload.get('query', '')
            return InlineKeyboardButton(text, switch_inline_query=query_text)
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
