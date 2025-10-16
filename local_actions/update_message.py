ACTION_METADATA = {
    "id": "update_message",
    "name": "更新菜单标题",
    "description": "使用输入的文本更新当前菜单的标题文本。",
    "inputs": [
        {"name": "text", "type": "string", "description": "要显示的新的菜单标题。"},
        {
            "name": "parse_mode",
            "type": "string",
            "required": False,
            "default": "html",
            "description": "设置菜单标题文本的解析模式。",
            "enum": ["html", "markdown", "markdownv2", "plain"],
            "enum_labels": {
                "html": "HTML（默认）",
                "markdown": "Markdown",
                "markdownv2": "MarkdownV2",
                "plain": "纯文本（不解析）",
            },
        },
    ],
    "outputs": [],
}


async def execute(text: str, parse_mode: str = "html") -> dict:
    """将输入的文本作为 new_text 返回以更新菜单标题。"""
    normalized = str(parse_mode or "html").strip().lower()
    if normalized in {"", "none", "plain", "text", "plaintext"}:
        normalized = "plain"
    elif normalized in {"markdown", "md"}:
        normalized = "markdown"
    elif normalized in {"markdownv2", "mdv2"}:
        normalized = "markdownv2"
    else:
        normalized = "html"

    return {"new_text": text, "parse_mode": normalized}
