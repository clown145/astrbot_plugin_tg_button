
ACTION_METADATA = {
    "id": "update_message",
    "name": "更新消息文本",
    "description": "使用输入的文本更新当前的消息。",
    "inputs": [
        {"name": "text", "type": "string", "description": "要显示的新消息文本。"}
    ],
    "outputs": []
}

async def execute(text: str) -> dict:
    """将输入的文本作为 new_text 返回以更新消息。"""
    return {
        "new_text": text
    }
