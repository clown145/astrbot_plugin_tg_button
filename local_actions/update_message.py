from ..telegram_format import build_parse_mode_input, canonical_parse_mode_alias


ACTION_METADATA = {
    "id": "update_message",
    "name": "更新菜单标题",
    "description": "使用输入的文本更新当前菜单的标题文本。",
    "inputs": [
        {"name": "text", "type": "string", "description": "要显示的新的菜单标题。"},
        build_parse_mode_input(
            description="更新菜单标题时使用的 Telegram 解析模式。",
            default="html",
        ),
    ],
    "outputs": [],
}


async def execute(text: str, parse_mode: str = "html") -> dict:
    """将输入的文本作为 new_text 返回以更新菜单标题。"""
    alias = canonical_parse_mode_alias(parse_mode)
    return {"new_text": text, "parse_mode": alias}
