# ACTION_METADATA 用于在 UI 中定义动作的属性
ACTION_METADATA = {
    "id": "show_notification",
    "name": "显示弹窗通知",
    "description": "在 Telegram 客户端顶部显示一个短暂的弹窗通知。适用于简短的、非阻塞的反馈。",
    "inputs": [
        {
            "name": "text",
            "type": "string",
            "description": "要显示的通知内容。",
            "default": "操作成功"
        },
        {
            "name": "show_alert",
            "type": "boolean",
            "description": "是否使用会强制用户确认的‘警报’样式。默认为否（短暂通知）。",
            "default": False
        }
    ],
    "outputs": []
}

async def execute(text: str, show_alert: bool = False):
    """
    执行显示通知的动作。
    主插件会拦截返回字典中的 'notification' 键并处理。
    """
    if not isinstance(text, str):
        text = str(text)

    return {
        "notification": {
            "text": text,
            "show_alert": bool(show_alert)
        }
    }
