"""
AstrBot 动态按钮框架的核心插件文件。
该文件定义了插件主类、管理插件的生命周期，并注册各类处理器，
将具体逻辑委托给其他模块执行。
"""

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType
from astrbot.api.message_components import Plain
from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
from astrbot.core.utils.session_waiter import session_waiter, SessionController

# --- Telegram 相关导入（带回退机制）---
try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
    from telegram.ext import Application, CallbackQueryHandler, ExtBot
except ImportError:  # 可选依赖
    logger.error("Telegram 库未安装，请在 AstrBot 环境中执行 pip install python-telegram-bot")
    Application, CallbackQueryHandler, ExtBot, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo = (None,) * 6

# --- 本地模块导入 ---
from dataclasses import dataclass, field
from typing import Any, Dict, Callable, List, Optional, Tuple

# 在类定义之前导入装饰器所需的命令名称
from .config import MENU_COMMAND, PLUGIN_NAME, build_settings

# 导入逻辑处理器
from . import commands
from . import handlers
from . import local_actions
from .actions import ActionExecutor
from .storage import ButtonStore, ButtonsModel, ButtonDefinition, MenuDefinition, WebAppDefinition
from .modular_actions import ModularActionRegistry


@dataclass
class RegisteredAction:
    """表示一个由插件注册的自定义动作。"""
    name: str
    function: Callable
    description: str
    parameters: Dict[str, Any]


class ActionRegistry:
    """存储和管理基于代码的自定义动作。"""
    def __init__(self, logger):
        self._actions: Dict[str, RegisteredAction] = {}
        self.logger = logger

    def register(self, name: str, function: Callable, description: str, params: Dict) -> bool:
        if name in self._actions:
            self.logger.warning(f"本地动作 '{name}' 已存在，无法重复注册。")
            return False
        self._actions[name] = RegisteredAction(name, function, description, params)
        self.logger.info(f"成功注册本地动作: '{name}'")
        return True

    def get(self, name: str) -> Optional[RegisteredAction]:
        return self._actions.get(name)

    def get_all(self) -> List[RegisteredAction]:
        return list(self._actions.values())


class TgButtonApi:
    """供其他插件与 TG Button 插件交互的公共 API。"""
    def __init__(self, registry: ActionRegistry):
        self._registry = registry

    def register_local_action(self, name: str, function: Callable, description: str, params: Dict):
        """
        允许其他插件注册自己的本地动作。
        参数:
            name: 动作的唯一名称。
            function: 执行此动作的可调用函数。
            description: 用户友好的描述。
            params: 描述所需参数的字典（用于 UI 生成）。
        """
        self._registry.register(name, function, description, params)

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
        # 使用配置模块中的函数构建设置
        self.settings = build_settings(config)
        self.logger = logger

        # 核心插件组件
        self.menu_command = self.settings["menu_command"]
        self.menu_header = self.settings["menu_header_text"]
        self.webui_enabled = self.settings["webui_enabled"]
        self.webui_exclusive = self.webui_enabled and self.settings["webui_exclusive"]
        self.button_store = ButtonStore(get_plugin_data_path(), logger=logger, default_header=self.menu_header)

        # --- 用于本地动作和 API 的新组件 ---
        self.action_registry = ActionRegistry(logger=logger)
        self.modular_actions_dir = get_plugin_data_path() / "modular_actions"
        self.modular_action_registry = ModularActionRegistry(logger=logger, actions_dir=self.modular_actions_dir)
        self.api = TgButtonApi(self.action_registry)

        self.action_executor = ActionExecutor(logger=logger, registry=self.action_registry, modular_registry=self.modular_action_registry)
        self.webui_server: Optional[WebUIServer] = None

        # Telegram 特定状态
        self._callback_handler: Optional[CallbackQueryHandler] = None
        self._telegram_application: Optional[Any] = None

        # 处理器使用的回调前缀
        self.CALLBACK_PREFIX_COMMAND = "tgbtn:cmd:"
        self.CALLBACK_PREFIX_MENU = "tgbtn:menu:"
        self.CALLBACK_PREFIX_BACK = "tgbtn:back:"
        self.CALLBACK_PREFIX_ACTION = "tgbtn:act:"
        self.CALLBACK_PREFIX_WORKFLOW = "tgbtn:wf:"

        logger.info(
            f"Dynamic button plugin loaded; menu command '/{self.menu_command}', WebUI={'enabled' if self.webui_enabled else 'disabled'}."
        )

        # 处理热重载
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        loop.create_task(self._post_init_after_reload())

    # --- 插件生命周期管理 ---

    async def _migrate_and_load_actions(self):
        """
        将插件内置的 local_actions 同步到用户数据目录下的 modular_actions，并加载所有模块化动作。
        此函数确保每次重载插件时，都会检查并更新预设动作文件。
        """
        source_dir = Path(__file__).parent / "local_actions"
        target_dir = self.modular_actions_dir

        if not source_dir.is_dir():
            # 如果插件内没有 local_actions 目录，则无需同步，直接加载即可
            await self.modular_action_registry.scan_and_load_actions()
            return

        target_dir.mkdir(parents=True, exist_ok=True)
        synced_count = 0
        updated_count = 0

        # 同步逻辑：遍历源目录中的所有 .py 文件
        for src_file in source_dir.glob("*.py"):
            if src_file.name.startswith("__"):
                continue  # 跳过 __init__.py 等特殊文件

            target_file = target_dir / src_file.name
            should_copy = False

            if not target_file.exists():
                # 如果目标文件不存在，直接复制
                should_copy = True
                synced_count += 1
            else:
                # 如果目标文件已存在，比较最后修改时间
                src_mtime = src_file.stat().st_mtime
                target_mtime = target_file.stat().st_mtime
                if src_mtime > target_mtime:
                    should_copy = True
                    updated_count += 1

            if should_copy:
                try:
                    content = src_file.read_text(encoding='utf-8')
                    target_file.write_text(content, encoding='utf-8')
                except Exception as e:
                    self.logger.error(f"同步预设动作文件 {src_file.name} 失败: {e}")

        if synced_count > 0:
            self.logger.info(f"成功同步 {synced_count} 个新的预设动作文件。")
        if updated_count > 0:
            self.logger.info(f"成功更新 {updated_count} 个已有的预设动作文件。")

        # 同步完成后，从目标目录加载所有模块化动作
        await self.modular_action_registry.scan_and_load_actions()

    async def _initialize_plugin_features(self):
        """
        统一的初始化函数，用于加载、迁移和注册插件的核心功能。
        避免在 _on_astrbot_loaded 和 _post_init_after_reload 中出现重复代码。
        """
        await self._migrate_and_load_actions()
        await self._ensure_webui()
        await self._register_telegram_callbacks()

    @filter.on_astrbot_loaded()
    async def _on_astrbot_loaded(self):
        await self._initialize_plugin_features()

    async def _post_init_after_reload(self):
        await asyncio.sleep(0.05)
        await self._initialize_plugin_features()

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

    # --- 内部设置 ---

    async def _ensure_webui(self):
        if not self.webui_enabled or self.webui_server:
            return
        server = WebUIServer(
            plugin=self,
            logger=logger,
            data_store=self.button_store,
            action_executor=self.action_executor,
            action_registry=self.action_registry,
            modular_action_registry=self.modular_action_registry,
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

        # 处理器函数现在是一个包装器，它会调用 handlers.py 中的逻辑
        handler = CallbackQueryHandler(self._handle_callback_query)
        application.add_handler(handler, group=1)
        self._callback_handler = handler
        self._telegram_application = application
        logger.info("Telegram 动态按钮回调处理器已注册。")

    # --- 事件处理器（包装器） ---

    async def _handle_callback_query(self, update, _context):
        """将回调查询处理委托给 handlers 模块的包装器。"""
        await handlers.handle_callback_query(self, update, _context)

    @filter.command(MENU_COMMAND)
    async def send_menu(self, event: AstrMessageEvent):
        """显示可交互的按钮菜单"""
        async for result in commands.send_menu(self, event):
            yield result

    # --- 内部辅助与服务方法 ---
    # 这些方法保留在主类中，因为外部的处理器和命令
    # 会通过 'plugin' 实例来使用它们。

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

    async def start_search_session(self, runtime: Any, **kwargs) -> Dict[str, Any]:
        prompt = kwargs.get("prompt", "请输入内容：")
        timeout = int(kwargs.get("timeout", 60))
        client = self._get_telegram_client()
        if not client or not runtime.chat_id or not runtime.message_id:
            return {"new_text": "执行失败：缺少上下文。"}

        try:
            await client.edit_message_text(
                chat_id=runtime.chat_id,
                message_id=runtime.message_id,
                text=prompt,
                reply_markup=None  # 等待输入时清除按钮
            )
        except Exception as e:
            self.logger.error(f"编辑消息以提示输入时出错: {e}")
            return {"new_text": f"执行失败: {e}"}

        # --- 创建一个伪事件来启动会话 ---
        platform = self.context.get_platform("telegram")
        fake_message = AstrBotMessage()
        fake_message.self_id = str(client.id)
        if runtime.chat_type == "private":
            fake_message.type = MessageType.FRIEND_MESSAGE
            fake_message.session_id = runtime.chat_id
        else:
            fake_message.type = MessageType.GROUP_MESSAGE
            session_id = f"{runtime.chat_id}#{runtime.thread_id}" if runtime.thread_id is not None else runtime.chat_id
            fake_message.group_id = session_id
            fake_message.session_id = session_id
        fake_message.sender = MessageMember(user_id=runtime.user_id or "", nickname=runtime.full_name or runtime.username or "")
        fake_message.message_str = "/fake_command_for_session"
        fake_message.timestamp = int(time.time())

        fake_event = TelegramPlatformEvent(
            message_str=fake_message.message_str,
            message_obj=fake_message,
            platform_meta=platform.meta(),
            session_id=fake_message.session_id,
            client=client,
        )
        fake_event.context = self.context
        # --- 会话等待器定义 ---

        @session_waiter(timeout=timeout)
        async def search_waiter(controller: SessionController, event: AstrMessageEvent):
            user_input = event.message_str
            await client.edit_message_text(
                chat_id=runtime.chat_id,
                message_id=runtime.message_id,
                text=f"模拟搜索完成。\n您的输入是: '{user_input}'\n\n现在您可以手动恢复菜单。"
            )
            controller.stop()

        try:
            await search_waiter(fake_event)
        except TimeoutError:
            await client.edit_message_text(
                chat_id=runtime.chat_id,
                message_id=runtime.message_id,
                text="输入超时，操作已取消。"
            )
        except Exception as e:
            self.logger.error(f"会话执行期间出错: {e}", exc_info=True)
            await client.edit_message_text(
                chat_id=runtime.chat_id,
                message_id=runtime.message_id,
                text=f"会话处理失败: {e}"
            )

        # 这个本地动作本身不需要向执行器返回任何东西，
        # 因为它自己处理所有用户交互。
        return {}


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
            if not button.payload.get('action_id'):
                return None
            return InlineKeyboardButton(text, callback_data=f"{self.CALLBACK_PREFIX_ACTION}{button.id}")
        if btn_type == 'workflow':
            if not button.payload.get('workflow_id'):
                return None
            return InlineKeyboardButton(text, callback_data=f"{self.CALLBACK_PREFIX_WORKFLOW}{button.id}")
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
