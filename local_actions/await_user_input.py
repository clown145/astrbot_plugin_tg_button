from typing import Any, Dict, List

ACTION_METADATA = {
    "id": "await_user_input",
    "name": "等待用户输入 (Await User Input)",
    "description": "提示用户在当前对话中输入内容，并在收到回复后继续工作流。",
    "inputs": [
        {
            "name": "prompt_template",
            "type": "string",
            "required": False,
            "default": "请输入内容：",
            "description": "显示给用户的提示消息（支持工作流上下文模板）。",
        },
        {
            "name": "prompt_display_mode",
            "type": "string",
            "required": False,
            "default": "button_label",
            "description": "提示展示方式：替换按钮标题、更新菜单标题或改写整条消息。",
            "enum": ["button_label", "menu_title", "message_text"],
            "enum_labels": {
                "button_label": "修改按钮标题",
                "menu_title": "更新菜单标题",
                "message_text": "替换消息文本",
            },
        },
        {
            "name": "timeout_seconds",
            "type": "integer",
            "required": False,
            "default": 60,
            "description": "等待用户输入的超时时间（秒）。",
        },
        {
            "name": "allow_empty",
            "type": "boolean",
            "required": False,
            "default": False,
            "description": "是否允许用户输入为空字符串。如果不允许则会重复提示。",
        },
        {
            "name": "retry_prompt_template",
            "type": "string",
            "required": False,
            "description": "当用户输入为空且不被允许时，重新提示的消息。留空则继续使用原始提示。",
        },
        {
            "name": "success_template",
            "type": "string",
            "required": False,
            "description": "收到用户输入后要显示的内容，可使用 {{ user_input }} 占位符。留空则保留提示文案。",
        },
        {
            "name": "timeout_template",
            "type": "string",
            "required": False,
            "default": "输入超时，操作已取消。",
            "description": "超时后显示的消息。留空则不修改提示。",
        },
        {
            "name": "cancel_keywords",
            "type": "string",
            "required": False,
            "description": "将这些关键字视为取消指令（换行或逗号分隔）。",
        },
        {
            "name": "cancel_template",
            "type": "string",
            "required": False,
            "description": "触发取消关键字后显示的消息。留空则提示保持不变。",
        },
        {
            "name": "parse_mode",
            "type": "string",
            "required": False,
            "default": "html",
            "description": "发送提示/结果时使用的 Telegram 解析模式。",
            "enum": ["html", "markdown", "markdownv2", "none"],
            "enum_labels": {
                "html": "HTML",
                "markdown": "Markdown",
                "markdownv2": "Markdown V2",
                "none": "纯文本",
            },
        },
    ],
    "outputs": [
        {
            "name": "user_input",
            "type": "string",
            "description": "用户最新一次的文本输入。",
        },
        {
            "name": "user_input_status",
            "type": "string",
            "description": "输入状态：success/timeout/cancelled/error。",
        },
        {
            "name": "user_input_is_timeout",
            "type": "boolean",
            "description": "是否因为超时而结束等待。",
        },
        {
            "name": "user_input_is_cancelled",
            "type": "boolean",
            "description": "是否因为取消关键字而结束等待。",
        },
        {
            "name": "user_input_message_id",
            "type": "string",
            "description": "用户输入消息的 ID（若可用）。",
        },
        {
            "name": "user_input_timestamp",
            "type": "integer",
            "description": "用户输入的时间戳（UNIX 秒，若可用）。",
        },
    ],
}


def _parse_keywords(raw_value: Any) -> List[str]:
    if not raw_value:
        return []
    if isinstance(raw_value, (list, tuple)):
        return [str(item).strip() for item in raw_value if str(item).strip()]
    text = str(raw_value).replace("\r", "\n")
    parts: List[str] = []
    for chunk in text.split("\n"):
        for section in chunk.split(","):
            section = section.strip()
            if section:
                parts.append(section)
    return parts


async def execute(
    plugin,
    *,
    runtime,
    prompt_template: str = "请输入内容：",
    prompt_display_mode: str = "button_label",
    timeout_seconds: Any = 60,
    allow_empty: bool = False,
    retry_prompt_template: str = "",
    success_template: str = "",
    timeout_template: str = "输入超时，操作已取消。",
    cancel_keywords: Any = None,
    cancel_template: str = "",
    parse_mode: str = "html",
) -> Dict[str, Any]:
    if plugin is None or runtime is None:
        return {
            "new_text": "等待用户输入失败：缺少插件上下文。",
            "user_input_status": "error",
            "user_input": "",
            "user_input_is_timeout": False,
            "user_input_is_cancelled": False,
        }

    keywords = _parse_keywords(cancel_keywords)

    try:
        timeout_value = int(timeout_seconds)
    except (TypeError, ValueError):
        timeout_value = 60

    try:
        result = await plugin.wait_for_user_input(
            runtime=runtime,
            prompt=prompt_template or "请输入内容：",
            timeout=timeout_value,
            allow_empty=bool(allow_empty),
            retry_prompt=retry_prompt_template or None,
            success_message=success_template or None,
            timeout_message=timeout_template or None,
            cancel_keywords=keywords,
            cancel_message=cancel_template or None,
            parse_mode=parse_mode or "html",
            display_mode=prompt_display_mode or "button_label",
        )
    except Exception as exc:  # Defensive logging
        logger = getattr(plugin, "logger", None)
        if logger:
            logger.error(f"等待用户输入动作执行失败: {exc}", exc_info=True)
        return {
            "new_text": f"等待用户输入失败: {exc}",
            "user_input_status": "error",
            "user_input": "",
            "user_input_is_timeout": False,
            "user_input_is_cancelled": False,
        }

    if not isinstance(result, dict):
        return {
            "new_text": "等待用户输入失败：返回结果无效。",
            "user_input_status": "error",
            "user_input": "",
            "user_input_is_timeout": False,
            "user_input_is_cancelled": False,
        }

    return result
