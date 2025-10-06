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
        with open(data_file, 'r', encoding='utf-8-sig') as f:
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
except json.JSONDecodeError as e:
    logger.error(f"解析配置文件 {PLUGIN_NAME}_config.json 失败: {e}，将使用默认值。")
    plugin_config = {}

MENU_COMMAND = plugin_config.get("menu_command", "menu")
MENU_HEADER = plugin_config.get("menu_header_text", "请选择功能：")
LAYOUT_MODE = plugin_config.get("button_layout_mode", "column")
try:
    BUTTONS_PER_LINE = int(plugin_config.get("buttons_per_line", 3))
    if BUTTONS_PER_LINE <= 0: BUTTONS_PER_LINE = 3
except (ValueError, TypeError):
    BUTTONS_PER_LINE = 3


@register(
    PLUGIN_NAME,
    "clown145",
    "一个可以使用telegram按钮的插件",
    "1.0.2",
    "https://github.com/clown145/astrbot_plugin_tg_button",
)
class DynamicButtonFrameworkPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.CALLBACK_PREFIX_CMD = "final_btn_cmd:"
        logger.info(f"动态按钮插件已加载，菜单指令为 '/{MENU_COMMAND}'。")

    @filter.on_astrbot_loaded()
    async def _initialize_telegram_callbacks(self):
        if not Application: return
        platform = self.context.get_platform("telegram")
        if not platform: return
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
                    fake_message.group_id, fake_message.session_id = "", chat_id
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
                fake_message.message_str, fake_message.raw_message, fake_message.timestamp, fake_message.message = \
                    command_text, update, int(query.message.date.timestamp()), [Plain(command_text)]
                fake_event = TelegramPlatformEvent(
                    message_str=command_text, message_obj=fake_message,
                    platform_meta=platform.meta(), session_id=fake_message.session_id, client=client
                )
                fake_event.context, fake_event.is_at_or_wake_command = self.context, True
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
        if event.get_platform_name() != "telegram": return
        buttons_data = load_buttons_data()
        if not buttons_data:
            yield event.plain_result("当前未配置任何按钮。")
            return
        all_buttons = [InlineKeyboardButton(b.get("text"), callback_data=f"{self.CALLBACK_PREFIX_CMD}{b.get('value')}") if b.get("type") == "command" else InlineKeyboardButton(b.get("text"), url=b.get("value")) for b in buttons_data if all((b.get("text"), b.get("type"), b.get("value")))]
        if not all_buttons:
            yield event.plain_result("按钮数据配置不正确，无法生成菜单。")
            return
        keyboard = [all_buttons[i:i + BUTTONS_PER_LINE] for i in range(0, len(all_buttons), BUTTONS_PER_LINE)] if LAYOUT_MODE == 'row' else [[b] for b in all_buttons]
        try:
            platform = self.context.get_platform("telegram")
            client: ExtBot = platform.get_client()
            chat_id_str = event.get_group_id() or event.get_sender_id()
            chat_id = chat_id_str.split('#')[0]
            thread_id = int(chat_id_str.split('#')[1]) if '#' in chat_id_str else None
            await client.send_message(chat_id=chat_id, text=MENU_HEADER, reply_markup=InlineKeyboardMarkup(keyboard), message_thread_id=thread_id)
        except Exception as e:
            logger.error(f"发送自定义菜单失败: {e}", exc_info=True)
            yield event.plain_result(f"发送菜单时出错，请查看后台日志。")
        event.stop_event()

    @filter.command("bind", alias={"绑定"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def bind_button(self, event: AstrMessageEvent):
        args_str = event.message_str.strip()
        arg_parts = args_str.split()
        if len(arg_parts) < 3:
            yield event.plain_result("格式错误或参数不足！\n格式: /bind <按钮文字> <类型> <值>\n例如: /bind 搜索谷歌 指令 search google")
            return
        actual_args = arg_parts[1:]
        type_keywords_map = {"指令": "command", "command": "command", "网址": "url", "url": "url"}
        found_keyword, keyword_index = None, -1
        for i, part in enumerate(actual_args):
            if part.lower() in type_keywords_map and i > 0 and i < len(actual_args) - 1:
                found_keyword, keyword_index = part, i
                break
        if not found_keyword:
            yield event.plain_result("格式错误或参数不足！\n格式: /bind <按钮文字> <类型> <值>\n类型必须是: 指令, command, 网址, url")
            return
        text = " ".join(actual_args[:keyword_index])
        value = " ".join(actual_args[keyword_index+1:])
        btn_type = type_keywords_map[found_keyword.lower()]
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
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def unbind_button(self, event: AstrMessageEvent):
        full_args = event.message_str.strip().split()
        if len(full_args) < 2:
            yield event.plain_result("参数缺失！请输入要解绑的按钮的完整文字。")
            return
        text = " ".join(full_args[1:])
        buttons = load_buttons_data()
        button_to_remove = next((b for b in buttons if b.get("text") == text), None)
        if button_to_remove:
            buttons.remove(button_to_remove)
            save_buttons_data(buttons)
            yield event.plain_result(f"🗑️ 按钮 '{text}' 已成功解绑！")
        else:
            yield event.plain_result(f"❓ 未找到名为 '{text}' 的按钮。")
