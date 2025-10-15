ACTION_METADATA = {
    "id": "update_message",
    "name": "更新菜单标题",
    "description": "使用输入的文本更新当前菜单的标题文本。",
    "inputs": [
        {"name": "text", "type": "string", "description": "要显示的新的菜单标题。"}
    ],
    "outputs": [],
}


async def execute(text: str) -> dict:
    """将输入的文本作为 new_text 返回以更新菜单标题。"""
    return {"new_text": text}
