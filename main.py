import asyncio
import json
from pathlib import Path
from typing import Dict, List

from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType
from astrbot.api.message_components import Plain
from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CallbackQueryHandler, ExtBot
except ImportError:
    logger.error("Telegram 库未安装，请在 AstrBot 环境中执行: pip install python-telegram-bot")
    Application, ExtBot, CallbackQueryHandler, InlineKeyboardMarkup, InlineKeyboardButton = None, None, None, None, None

PLUGIN_NAME = "astrbot_plugin_tg_button"

def get_plugin_data_path() -> Path:
    return StarTools.get_data_dir(PLUGIN_NAME)

def load_buttons_data() -> List[Dict]:
    data_file = get_plugin_data_path() / "buttons.json"
    if not data_file.exists():
        return []
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"读取按钮数据失败: {e}")
        return []

def save_buttons_data(data: List[Dict]):
    try:
        data_path = get_plugin_data_path()
        data_path.mkdir(parents=True, exist_ok=True)
        with open(data_path / "buttons.json", 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"保存按钮数据失败: {e}")

try:
    with open(f"data/config/{PLUGIN_NAME}_config.json", "r", encoding="utf-8-sig") as f:
        plugin_config = json.load(f)
except FileNotFoundError:
    logger.warning("按钮框架插件的配置文件未找到，将使用默认值。")
    plugin_config = {}

MENU_COMMAND = plugin_config.get("menu_command", "menu")
BIND_PERMISSION_LEVEL = plugin_config.get("bind_permission", "admin")
PERMISSION_VALUE = filter.PermissionType.ADMIN if BIND_PERMISSION_LEVEL == "admin" else filter.PermissionType.USER


@register(
    PLUGIN_NAME,
    "clown145",
    "一个可以使用telegram按钮的插件",
    "1.0.0",
    "https://github.com/clown145/astrbot_plugin_tg_button",
)
class DynamicButtonFrameworkPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.CALLBACK_PREFIX_CMD = "final_btn_cmd:"
        # 移除 asyncio.create_task 和旧的初始化方法调用
        logger.info(f"动态按钮插件已加载，菜单指令为 '/{MENU_COMMAND}'。回调将在 AstrBot 完全启动后注册。")

    @filter.on_astrbot_loaded()
    async def _initialize_telegram_callbacks(self):
        """
        在 AstrBot 完全加载后安全地注册 Telegram 回调。
        """
        if not Application:
            logger.error("Dynamic Button Framework 插件因缺少 Telegram 库而无法注册回调。")
            return
        
        platform = self.context.get_platform("telegram")
        if not platform:
            logger.warning("未找到 Telegram 平台实例，无法注册按钮回调。")
            return

        async def button_callback_handler(update, context):
            query = update.callback_query
            if not query or not query.data or not query.data.startswith(self.CALLBACK_PREFIX_CMD):
                if query: await query.answer()
                return

            await query.answer()
            command_text = query.data[len(self.CALLBACK_PREFIX_CMD):]
            logger.info(f"用户 {query.from_user.id} 通过按钮触发指令: {command_text}")
            
            try:
                client: ExtBot = platform.get_client()
                fake_message = AstrBotMessage()
                
                is_private = query.message.chat.type == 'private'
                chat_id = str(query.message.chat.id)
                thread_id = str(query.message.message_thread_id) if not is_private and query.message.message_thread_id else None

                if is_private:
                    fake_message.type = MessageType.FRIEND_MESSAGE
                    fake_message.group_id = ""
                    fake_message.session_id = chat_id
                else:
                    fake_message.type = MessageType.GROUP_MESSAGE
                    fake_message.group_id = f"{chat_id}#{thread_id}" if thread_id else chat_id
                    fake_message.session_id = fake_message.group_id
                
                fake_message.self_id = str(client.id)
                fake_message.message_id = str(query.message.message_id) + "_btn_trigger"
                fake_message.sender = MessageMember(
                    user_id=str(query.from_user.id), 
                    nickname=query.from_user.full_name or query.from_user.username or "Unknown"
                )
                fake_message.message_str = command_text
                fake_message.raw_message = update
                fake_message.timestamp = int(query.message.date.timestamp())
                fake_message.message = [Plain(command_text)]
                
                fake_event = TelegramPlatformEvent(
                    message_str=command_text,
                    message_obj=fake_message,
                    platform_meta=platform.meta(),
                    session_id=fake_message.session_id,
                    client=client
                )
                fake_event.context = self.context
                fake_event.is_at_or_wake_command = True
                
                self.context.get_event_queue().put_nowait(fake_event)

            except Exception as e:
                logger.error(f"模拟事件并重新分发时出错: {e}", exc_info=True)

        if hasattr(platform, 'application'):
            platform.application.add_handler(CallbackQueryHandler(button_callback_handler), group=1)
            logger.info("成功注册 Telegram 动态按钮回调处理器。")
        else:
            logger.error("无法注册回调处理器：platform 对象没有 'application' 属性。")
    

    @filter.command(MENU_COMMAND)
    async def send_menu(self, event: AstrMessageEvent):
        if event.get_platform_name() != "telegram":
            return
        buttons_data = load_buttons_data()
        if not buttons_data:
            yield event.plain_result("当前未配置任何按钮。")
            return
        
        keyboard = []
        for button_def in buttons_data:
            text, btn_type, value = button_def.get("text"), button_def.get("type"), button_def.get("value")
            if not all((text, btn_type, value)):
                continue
            
            button = None
            if btn_type == "command":
                button = InlineKeyboardButton(text, callback_data=f"{self.CALLBACK_PREFIX_CMD}{value}")
            elif btn_type == "url":
                button = InlineKeyboardButton(text, url=value)
            
            if button:
                keyboard.append([button])

        if not keyboard:
            yield event.plain_result("按钮数据配置不正确，无法生成菜单。")
            return
        
        try:
            platform = self.context.get_platform("telegram")
            client: ExtBot = platform.get_client()
            chat_id_str = event.get_group_id() or event.get_sender_id()
            chat_id = chat_id_str.split('#')[0]
            thread_id = int(chat_id_str.split('#')[1]) if '#' in chat_id_str else None
            
            await client.send_message(
                chat_id=chat_id, 
                text="请选择功能：", 
                reply_markup=InlineKeyboardMarkup(keyboard), 
                message_thread_id=thread_id
            )
        except Exception as e:
            logger.error(f"发送自定义菜单失败: {e}", exc_info=True)
            yield event.plain_result(f"发送菜单时出错，请查看后台日志。")
        
        event.stop_event()

    @filter.command("bind", alias={"绑定"})
    @filter.permission_type(PERMISSION_VALUE) 
    async def bind_button(self, event: AstrMessageEvent, text: str, btn_type: str, value: str):
        btn_type_map = {"指令": "command", "网址": "url"}
        btn_type = btn_type_map.get(btn_type.lower(), btn_type.lower())
        
        if btn_type not in ["command", "url"]:
            yield event.plain_result("绑定失败：类型必须是 'command'/'指令' 或 'url'/'网址'。")
            return
            
        buttons = load_buttons_data()
        found = False
        for button in buttons:
            if button.get("text") == text:
                button.update({"type": btn_type, "value": value})
                found = True
                break
        if not found:
            buttons.append({"text": text, "type": btn_type, "value": value})
        
        save_buttons_data(buttons)
        yield event.plain_result(f"✅ 按钮 '{text}' 已成功绑定！")

    @filter.command("unbind", alias={"解绑"})
    @filter.permission_type(PERMISSION_VALUE)
    async def unbind_button(self, event: AstrMessageEvent, text: str):
        buttons = load_buttons_data()
        button_to_remove = next((b for b in buttons if b.get("text") == text), None)
        
        if button_to_remove:
            buttons.remove(button_to_remove)
            save_buttons_data(buttons)
            yield event.plain_result(f"🗑️ 按钮 '{text}' 已成功解绑！")
        else:
            yield event.plain_result(f"❓ 未找到名为 '{text}' 的按钮。")
