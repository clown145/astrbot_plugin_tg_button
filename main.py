"""
AstrBot 动态按钮框架的核心插件文件。
该文件定义了插件主类、管理插件的生命周期，并注册各类处理器，
将具体逻辑委托给其他模块执行。
"""

import asyncio
import html
import hashlib
import os
import re
import shutil
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
    logger.error(
        "Telegram 库未安装，请在 AstrBot 环境中执行 pip install python-telegram-bot"
    )
    (
        Application,
        CallbackQueryHandler,
        ExtBot,
        InlineKeyboardButton,
        InlineKeyboardMarkup,
        WebAppInfo,
    ) = (None,) * 6

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
from .storage import (
    ButtonStore,
    ButtonsModel,
    ButtonDefinition,
    MenuDefinition,
    WebAppDefinition,
)
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

    def register(
        self, name: str, function: Callable, description: str, params: Dict
    ) -> bool:
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

    def register_local_action(
        self, name: str, function: Callable, description: str, params: Dict
    ):
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


def _get_file_hash(path: Path) -> str:
    """计算文件的 SHA256 哈希值。"""
    sha256 = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()
    except IOError:
        return ""


@register(
    PLUGIN_NAME,
    "clown145",
    "一个可以通过 Telegram 按钮与自定义 WebUI 管理的插件",
    "1.3.0",
    "https://github.com/clown145/astrbot_plugin_tg_button",
)
class DynamicButtonFrameworkPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        # 使用配置模块中的函数构建设置
        self.settings = build_settings(config)
        self.logger = logger

        # --- 核心路径和目录设置 ---
        self.plugin_data_dir = get_plugin_data_path()
        self.temp_dir = self.plugin_data_dir / "temp"
        os.makedirs(self.temp_dir, exist_ok=True)
        self.logger.info(f"临时文件目录已确保存在: {self.temp_dir}")

        # 核心插件组件
        self.menu_command = self.settings["menu_command"]
        self.menu_header = self.settings["menu_header_text"]
        self.webui_enabled = self.settings["webui_enabled"]
        self.webui_exclusive = self.webui_enabled and self.settings["webui_exclusive"]
        self.button_store = ButtonStore(
            self.plugin_data_dir, logger=logger, default_header=self.menu_header
        )

        # --- 用于本地动作和 API 的新组件 ---
        self.action_registry = ActionRegistry(logger=logger)
        self.modular_actions_dir = self.plugin_data_dir / "modular_actions"
        self.modular_action_registry = ModularActionRegistry(
            logger=logger, actions_dir=self.modular_actions_dir
        )
        self.api = TgButtonApi(self.action_registry)

        self.action_executor = ActionExecutor(
            logger=logger,
            registry=self.action_registry,
            modular_registry=self.modular_action_registry,
        )
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
                # 如果目标文件已存在，比较文件内容的哈希值
                src_hash = _get_file_hash(src_file)
                target_hash = _get_file_hash(target_file)
                if src_hash != target_hash:
                    should_copy = True
                    updated_count += 1

            if should_copy:
                try:
                    content = src_file.read_text(encoding="utf-8")
                    target_file.write_text(content, encoding="utf-8")
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
                self._telegram_application.remove_handler(
                    self._callback_handler, group=1
                )
            except Exception as exc:
                logger.error(f"移除 Telegram 回调处理器时出错: {exc}", exc_info=True)
            self._callback_handler = None
            self._telegram_application = None
        if self.webui_server:
            await self.webui_server.stop()
            self.webui_server = None
        await self.action_executor.close()

        # --- 新增的缓存清理逻辑 ---
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                self.logger.info(f"插件停用/重载，已清空临时文件目录: {self.temp_dir}")
        except Exception as exc:
            self.logger.error(
                f"清理临时文件目录 {self.temp_dir} 失败: {exc}", exc_info=True
            )
        # --- 清理逻辑结束 ---

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
        if (
            not platform
            or not (client := self._get_telegram_client())
            or not (message := query.message)
        ):
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
            nickname=(sender.full_name if sender else None)
            or (sender.username if sender else "Unknown"),
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

    async def wait_for_user_input(
        self,
        runtime: Any,
        *,
        prompt: str = "请输入内容：",
        timeout: int = 60,
        allow_empty: bool = False,
        retry_prompt: Optional[str] = None,
        success_message: Optional[str] = None,
        timeout_message: Optional[str] = None,
        cancel_keywords: Optional[List[str]] = None,
        cancel_message: Optional[str] = None,
        parse_mode: str = "html",
        display_mode: str = "button_label",
    ) -> Dict[str, Any]:
        client = self._get_telegram_client()
        chat_id = getattr(runtime, "chat_id", None)
        message_id = getattr(runtime, "message_id", None)
        if not client or not chat_id or not message_id:
            return {
                "new_text": "等待用户输入失败：缺少聊天上下文。",
                "user_input": "",
                "user_input_status": "error",
                "user_input_is_timeout": False,
                "user_input_is_cancelled": False,
            }

        def _map_parse_mode(value: Optional[str]) -> Optional[str]:
            if not value:
                return "HTML"
            lowered = value.strip().lower()
            if lowered in ("", "none", "plain"):
                return None
            if lowered in ("markdownv2", "mdv2"):
                return "MarkdownV2"
            if lowered in ("markdown", "md"):
                return "Markdown"
            return "HTML"

        parse_mode_value = (parse_mode or "html").strip().lower()

        def _normalize_button_label(raw_text: Optional[str], fallback: Optional[str] = None) -> str:
            base_text = str(raw_text or "").strip()
            if parse_mode_value == "html" and base_text:
                base_text = html.unescape(re.sub(r"<[^>]+>", "", base_text))
            elif parse_mode_value in ("markdown", "md", "markdownv2", "mdv2") and base_text:
                cleaned = re.sub(r"[*_`~]", "", base_text)
                if parse_mode_value in ("markdownv2", "mdv2"):
                    cleaned = cleaned.translate(
                        str.maketrans("", "", "\\[]()>\"")
                    )
                base_text = cleaned.strip()
            if not base_text:
                base_text = str(raw_text or "").strip()
            if not base_text and fallback:
                base_text = str(fallback).strip()
            if len(base_text) > 64:
                base_text = base_text[:61] + "..."
            return base_text

        tg_parse_mode = _map_parse_mode(parse_mode)
        prompt_text = prompt or "请输入内容："

        display_mode_value = str(display_mode or "button_label").strip().lower()
        if display_mode_value in {"menu_title", "menu_header", "header", "menu"}:
            normalized_mode = "menu_title"
        elif display_mode_value in {"message_text", "message", "text"}:
            normalized_mode = "message_text"
        else:
            normalized_mode = "button_label"

        button_label_mode = normalized_mode == "button_label"
        menu_title_mode = normalized_mode == "menu_title"
        message_text_mode = normalized_mode == "message_text"

        variables: Dict[str, Any] = getattr(runtime, "variables", {}) or {}
        menu_id = variables.get("menu_id")
        button_id = variables.get("button_id")
        original_button_text = variables.get("button_text")
        original_menu_header = (
            variables.get("menu_header_text")
            or variables.get("menu_header")
            or variables.get("menu_text")
        )
        callback_data = getattr(runtime, "callback_data", "") or ""
        if not button_id and callback_data:
            for prefix in (
                self.CALLBACK_PREFIX_WORKFLOW,
                self.CALLBACK_PREFIX_ACTION,
                self.CALLBACK_PREFIX_COMMAND,
                self.CALLBACK_PREFIX_MENU,
                self.CALLBACK_PREFIX_BACK,
            ):
                if callback_data.startswith(prefix):
                    button_id = callback_data[len(prefix) :]
                    break

        button_snapshot: Optional[ButtonsModel] = None
        button_menu: Optional[MenuDefinition] = None

        if button_label_mode or menu_title_mode:
            try:
                button_snapshot = await self.button_store.get_snapshot()
            except Exception as exc:
                self.logger.error(f"获取按钮快照失败: {exc}", exc_info=True)
            else:
                if menu_id:
                    button_menu = button_snapshot.menus.get(menu_id)
                if not button_menu and button_id:
                    button_menu = self._find_menu_for_button(button_snapshot, button_id)
                    if button_menu:
                        menu_id = button_menu.id
                if button_id and not original_button_text:
                    button_def = button_snapshot.buttons.get(button_id)
                    if button_def:
                        original_button_text = button_def.text
                if not original_menu_header:
                    original_menu_header = (
                        (button_menu.header if button_menu else None)
                        or self.menu_header
                    )

        if button_label_mode and not (button_snapshot and button_menu and button_id):
            button_label_mode = False
            message_text_mode = True
        if menu_title_mode and not (button_snapshot and button_menu):
            menu_title_mode = False
            message_text_mode = True

        async def _set_button_label(
            snapshot: ButtonsModel,
            menu: MenuDefinition,
            label_text: Optional[str],
        ) -> bool:
            if not button_id:
                return False
            overrides_map: Dict[str, Dict[str, Any]] = {}
            if label_text is not None:
                overrides_map = self._resolve_button_overrides(
                    snapshot,
                    menu,
                    [{"target": "self", "text": label_text}],
                    button_id,
                )
            markup, _ = self._build_menu_markup(menu.id, snapshot, overrides=overrides_map)
            if markup is None:
                return False
            try:
                await client.edit_message_reply_markup(
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=markup,
                )
                return True
            except Exception as exc:
                self.logger.error(f"更新按钮标题失败: {exc}", exc_info=True)
                return False

        async def _set_menu_header(
            snapshot: ButtonsModel,
            menu: MenuDefinition,
            header_text: Optional[str],
        ) -> bool:
            markup, _ = self._build_menu_markup(menu.id, snapshot)
            if markup is None:
                return False
            try:
                await client.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=header_text or self.menu_header,
                    parse_mode=tg_parse_mode,
                    reply_markup=markup,
                )
                return True
            except Exception as exc:
                self.logger.error(f"更新菜单标题失败: {exc}", exc_info=True)
                return False

        if button_label_mode:
            prompt_label = _normalize_button_label(prompt_text, original_button_text)
            if not prompt_label or not await _set_button_label(
                button_snapshot, button_menu, prompt_label
            ):
                button_label_mode = False
                message_text_mode = True

        if menu_title_mode:
            if not await _set_menu_header(button_snapshot, button_menu, prompt_text):
                menu_title_mode = False
                message_text_mode = True

        if message_text_mode and not button_label_mode and not menu_title_mode:
            try:
                await client.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=prompt_text,
                    parse_mode=tg_parse_mode,
                    reply_markup=None,
                )
            except Exception as exc:
                self.logger.error(f"发送等待输入提示失败: {exc}", exc_info=True)
                return {
                    "new_text": f"等待用户输入失败: {exc}",
                    "user_input": "",
                    "user_input_status": "error",
                    "user_input_is_timeout": False,
                    "user_input_is_cancelled": False,
                }

        timeout = max(int(timeout or 0), 1)
        cancel_set = {kw.strip().lower() for kw in (cancel_keywords or []) if kw.strip()}
        platform = self.context.get_platform("telegram")
        if not platform:
            return {
                "new_text": "等待用户输入失败：未找到 Telegram 平台。",
                "user_input": "",
                "user_input_status": "error",
                "user_input_is_timeout": False,
                "user_input_is_cancelled": False,
            }

        fake_message = AstrBotMessage()
        fake_message.self_id = str(client.id)
        if getattr(runtime, "chat_type", None) == "private":
            fake_message.type = MessageType.FRIEND_MESSAGE
            fake_message.session_id = chat_id
        else:
            fake_message.type = MessageType.GROUP_MESSAGE
            session_id = (
                f"{chat_id}#{getattr(runtime, 'thread_id', None)}"
                if getattr(runtime, "thread_id", None) is not None
                else chat_id
            )
            fake_message.group_id = session_id
            fake_message.session_id = session_id
        fake_message.sender = MessageMember(
            user_id=getattr(runtime, "user_id", "") or "",
            nickname=(
                getattr(runtime, "full_name", None)
                or getattr(runtime, "username", None)
                or ""
            ),
        )
        fake_message.message_str = "/__wait_for_input__"
        fake_message.timestamp = int(time.time())

        fake_event = TelegramPlatformEvent(
            message_str=fake_message.message_str,
            message_obj=fake_message,
            platform_meta=platform.meta(),
            session_id=fake_message.session_id,
            client=client,
        )
        fake_event.context = self.context

        captured: Dict[str, Any] = {
            "text": "",
            "message_id": None,
            "timestamp": None,
        }
        outcome = "timeout"

        def _render_user_template(template: Optional[str], user_text: str) -> Optional[str]:
            if not template:
                return None
            return (
                template.replace("{{ user_input }}", user_text)
                .replace("{{user_input}}", user_text)
            )

        @session_waiter(timeout=timeout, record_history_chains=False)
        async def user_input_waiter(
            controller: SessionController, event: AstrMessageEvent
        ):
            nonlocal outcome
            text = event.message_str or ""
            stripped = text.strip()
            lowered = stripped.lower()

            if cancel_set and lowered in cancel_set:
                captured["text"] = text
                msg_obj = getattr(event, "message_obj", None)
                captured["message_id"] = getattr(msg_obj, "message_id", None)
                captured["timestamp"] = getattr(msg_obj, "timestamp", None)
                outcome = "cancelled"
                controller.stop()
                return

            if not stripped and not allow_empty:
                retry_text = retry_prompt or prompt_text
                if button_label_mode and button_snapshot and button_menu:
                    retry_label = _normalize_button_label(
                        retry_text, original_button_text or prompt_text
                    )
                    await _set_button_label(button_snapshot, button_menu, retry_label)
                elif menu_title_mode and button_snapshot and button_menu:
                    await _set_menu_header(button_snapshot, button_menu, retry_text)
                else:
                    try:
                        await client.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=retry_text,
                            parse_mode=tg_parse_mode,
                            reply_markup=None,
                        )
                    except Exception as retry_exc:
                        self.logger.error(
                            f"更新等待输入提示失败: {retry_exc}", exc_info=True
                        )
                controller.keep(timeout=timeout, reset_timeout=True)
                return

            msg_obj = getattr(event, "message_obj", None)
            captured["text"] = text
            captured["message_id"] = getattr(msg_obj, "message_id", None)
            captured["timestamp"] = getattr(msg_obj, "timestamp", None)
            outcome = "success"
            controller.stop()

        try:
            await user_input_waiter(fake_event)
        except TimeoutError:
            outcome = "timeout"
        except Exception as exc:
            self.logger.error(f"等待用户输入时发生错误: {exc}", exc_info=True)
            return {
                "new_text": f"等待用户输入失败: {exc}",
                "user_input": "",
                "user_input_status": "error",
                "user_input_is_timeout": False,
                "user_input_is_cancelled": False,
            }

        user_input_text = captured.get("text", "")
        timed_out = outcome == "timeout"
        cancelled = outcome == "cancelled"
        final_text: Optional[str] = None
        button_overrides: List[Dict[str, Any]] = []

        if button_label_mode:
            label_source: Optional[str]
            if outcome == "success":
                label_source = _render_user_template(success_message, user_input_text)
            elif outcome == "timeout":
                label_source = timeout_message or "输入超时，操作已取消。"
            elif outcome == "cancelled":
                label_source = cancel_message or timeout_message or prompt_text
            else:
                label_source = None

            final_label = _normalize_button_label(
                label_source,
                original_button_text or prompt_text,
            )

            if button_id and menu_id and final_label:
                try:
                    latest_snapshot = await self.button_store.get_snapshot()
                except Exception as exc:
                    self.logger.error(f"刷新按钮快照失败: {exc}", exc_info=True)
                    latest_snapshot = None
                    latest_menu = None
                else:
                    latest_menu = (
                        latest_snapshot.menus.get(menu_id)
                        if latest_snapshot
                        else None
                    )
                    if latest_snapshot and not latest_menu and button_id:
                        latest_menu = self._find_menu_for_button(
                            latest_snapshot, button_id
                        )
                if latest_snapshot and latest_menu:
                    await _set_button_label(latest_snapshot, latest_menu, final_label)
                button_overrides.append(
                    {"target": "self", "text": final_label, "temporary": True}
                )
        elif menu_title_mode:
            if outcome == "success":
                final_text = _render_user_template(success_message, user_input_text)
            elif outcome == "timeout":
                final_text = timeout_message or "输入超时，操作已取消。"
            elif outcome == "cancelled":
                final_text = cancel_message or timeout_message or prompt_text

            if not final_text:
                final_text = original_menu_header or prompt_text

            latest_snapshot: Optional[ButtonsModel] = None
            latest_menu: Optional[MenuDefinition] = None
            try:
                latest_snapshot = await self.button_store.get_snapshot()
            except Exception as exc:
                self.logger.error(f"刷新按钮快照失败: {exc}", exc_info=True)
            else:
                if menu_id:
                    latest_menu = latest_snapshot.menus.get(menu_id)
                if not latest_menu and button_id:
                    latest_menu = self._find_menu_for_button(latest_snapshot, button_id)
            if latest_snapshot and latest_menu and final_text:
                await _set_menu_header(latest_snapshot, latest_menu, final_text)
            final_text = final_text or original_menu_header or prompt_text
        else:
            if outcome == "success":
                final_text = _render_user_template(success_message, user_input_text)
            elif outcome == "timeout":
                final_text = timeout_message or "输入超时，操作已取消。"
            elif outcome == "cancelled":
                final_text = cancel_message or timeout_message or prompt_text

            if final_text:
                try:
                    await client.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=final_text,
                        parse_mode=tg_parse_mode,
                        reply_markup=None,
                    )
                except Exception as exc:
                    self.logger.error(f"更新等待输入结果失败: {exc}", exc_info=True)

        result: Dict[str, Any] = {
            "user_input": user_input_text,
            "user_input_status": outcome if outcome != "timeout" else "timeout",
            "user_input_is_timeout": timed_out,
            "user_input_is_cancelled": cancelled,
        }

        if captured.get("message_id") is not None:
            result["user_input_message_id"] = str(captured["message_id"])
        if captured.get("timestamp") is not None:
            result["user_input_timestamp"] = captured["timestamp"]

        if menu_title_mode and final_text:
            result["new_text"] = final_text
            result["parse_mode"] = parse_mode or "html"
            result["should_edit_message"] = True
        elif final_text and not button_label_mode:
            result["new_text"] = final_text
            result["parse_mode"] = parse_mode or "html"

        if button_overrides:
            result["button_overrides"] = button_overrides

        return result

    async def start_search_session(self, runtime: Any, **kwargs) -> Dict[str, Any]:
        """
        [!!] 核心风险点：事件模拟 (Event Faking) [!!]
        此方法与 `_dispatch_command` 类似，通过构建一个伪事件对象 `fake_event`
        来启动一个 `session_waiter`。这是为了在一个异步的、由按钮触发的工作流中，
        能够暂停并等待用户的下一次消息输入。

        风险:
        - 与 `_dispatch_command` 相同的脆弱性，强依赖 `AstrBot` 内部事件结构。
        - 如果 `session_waiter` 的工作机制在未来版本中改变，此代码可能失效。

        保留原因:
        - 这是在无状态的按钮动作中，实现“等待用户输入”这一有状态交互的唯一方式。
        """
        prompt = kwargs.get("prompt", "请输入内容：")
        timeout = int(kwargs.get("timeout", 60))
        allow_empty = bool(kwargs.get("allow_empty", False))
        retry_prompt = kwargs.get("retry_prompt")
        success_template = kwargs.get(
            "success_message",
            "模拟搜索完成。\n您的输入是: '{{ user_input }}'\n\n现在您可以手动恢复菜单。",
        )
        timeout_template = kwargs.get("timeout_message", "输入超时，操作已取消。")
        cancel_template = kwargs.get("cancel_message")
        cancel_keywords = kwargs.get("cancel_keywords")
        if isinstance(cancel_keywords, str):
            cancel_keywords = [
                item.strip()
                for item in cancel_keywords.replace("\r", "\n").splitlines()
                if item.strip()
            ]
        parse_mode = kwargs.get("parse_mode", "html")
        display_mode = kwargs.get("display_mode") or "message_text"

        return await self.wait_for_user_input(
            runtime,
            prompt=prompt,
            timeout=timeout,
            allow_empty=allow_empty,
            retry_prompt=retry_prompt,
            success_message=success_template,
            timeout_message=timeout_template,
            cancel_keywords=cancel_keywords,
            cancel_message=cancel_template,
            parse_mode=parse_mode,
            display_mode=display_mode,
        )

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
            snapshot.buttons.get(btn_id)
            for btn_id in menu.items
            if snapshot.buttons.get(btn_id)
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

            def add_widget(
                row_index: int, col_index: int, widget: InlineKeyboardButton
            ) -> None:
                row_map.setdefault(row_index, []).append((col_index, widget))

            for btn in button_entities:
                override = overrides.get(btn.id)
                widget = self._create_inline_button(btn, snapshot, override)
                if not widget:
                    continue
                layout_override = override.get("layout") if override else None
                layout_row = (
                    layout_override.get("row")
                    if layout_override and "row" in layout_override
                    else btn.layout.row
                )
                layout_col = (
                    layout_override.get("col")
                    if layout_override and "col" in layout_override
                    else btn.layout.col
                )
                add_widget(layout_row, layout_col, widget)

            for row_idx in sorted(row_map.keys()):
                ordered = [
                    widget
                    for _, widget in sorted(row_map[row_idx], key=lambda item: item[0])
                ]
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
            if override and override.get("layout"):
                return False
        return True

    def _resolve_web_app_url(self, web_app: WebAppDefinition) -> Optional[str]:
        if web_app.kind == "external":
            return web_app.url
        return web_app.url or ""

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
            target = entry.get("target", "self")
            base = {k: v for k, v in entry.items() if k != "target"}
            if not base:
                continue
            target_ids = self._resolve_override_targets(
                snapshot, menu, target, current_button_id
            )
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
            target = "self"
        lowered = target.lower()
        if lowered == "self":
            return [current_button_id] if current_button_id in snapshot.buttons else []
        if lowered.startswith("id:"):
            candidate = target.split(":", 1)[1]
            return [candidate] if candidate in snapshot.buttons else []
        if lowered.startswith("button:"):
            candidate = target.split(":", 1)[1]
            return [candidate] if candidate in snapshot.buttons else []
        if lowered.startswith("index:"):
            try:
                idx = int(target.split(":", 1)[1])
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
        text = override.get("text") or button.text or "未命名"
        if override.get("switch_inline_query") or override.get(
            "switch_inline_query_current_chat"
        ):
            return InlineKeyboardButton(
                text,
                switch_inline_query=override.get("switch_inline_query"),
                switch_inline_query_current_chat=override.get(
                    "switch_inline_query_current_chat"
                ),
            )
        raw_callback = override.get("raw_callback_data")
        if raw_callback:
            return InlineKeyboardButton(text, callback_data=raw_callback)
        btn_type = (override.get("type") or button.type or "command").lower()
        if btn_type == "raw":
            callback_data = override.get("callback_data") or button.payload.get(
                "callback_data"
            )
            if not callback_data:
                return None
            return InlineKeyboardButton(text, callback_data=callback_data)
        if btn_type == "command":
            if not button.payload.get("command"):
                return None
            return InlineKeyboardButton(
                text, callback_data=f"{self.CALLBACK_PREFIX_COMMAND}{button.id}"
            )
        if btn_type == "url":
            url = override.get("url") or button.payload.get("url")
            if not url:
                return None
            return InlineKeyboardButton(text, url=url)
        if btn_type == "submenu":
            target = override.get("menu_id") or button.payload.get("menu_id")
            if not target:
                return None
            return InlineKeyboardButton(
                text, callback_data=f"{self.CALLBACK_PREFIX_MENU}{target}"
            )
        if btn_type == "action":
            if not button.payload.get("action_id"):
                return None
            return InlineKeyboardButton(
                text, callback_data=f"{self.CALLBACK_PREFIX_ACTION}{button.id}"
            )
        if btn_type == "workflow":
            if not button.payload.get("workflow_id"):
                return None
            return InlineKeyboardButton(
                text, callback_data=f"{self.CALLBACK_PREFIX_WORKFLOW}{button.id}"
            )
        if btn_type == "inline_query":
            query_text = override.get("query") or button.payload.get("query", "")
            return InlineKeyboardButton(
                text, switch_inline_query_current_chat=query_text
            )
        if btn_type == "switch_inline_query":
            query_text = override.get("query") or button.payload.get("query", "")
            return InlineKeyboardButton(text, switch_inline_query=query_text)
        if btn_type == "web_app":
            web_app_id = override.get("web_app_id") or button.payload.get("web_app_id")
            url = (
                override.get("web_app_url")
                or override.get("url")
                or button.payload.get("url")
            )
            if web_app_id:
                web_app = snapshot.web_apps.get(web_app_id)
                if web_app:
                    resolved = self._resolve_web_app_url(web_app)
                    if resolved:
                        url = resolved
            if not url or not WebAppInfo:
                return None
            return InlineKeyboardButton(text, web_app=WebAppInfo(url=url))
        if btn_type == "back":
            target = (
                override.get("menu_id")
                or button.payload.get("menu_id")
                or button.payload.get("target_menu")
            )
            if not target:
                return None
            return InlineKeyboardButton(
                text, callback_data=f"{self.CALLBACK_PREFIX_BACK}{target}"
            )
        return None

    def _find_menu_for_button(
        self, snapshot: ButtonsModel, button_id: str
    ) -> Optional[MenuDefinition]:
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

