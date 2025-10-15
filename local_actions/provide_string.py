ACTION_METADATA = {
    "id": "provide_static_string",
    "name": "提供静态字符串",
    "description": "提供一个在节点中定义的静态字符串作为输出。",
    "inputs": [
        {"name": "value", "type": "string", "description": "要输出的字符串值。"}
    ],
    "outputs": [{"name": "output", "type": "string", "description": "输出的字符串。"}],
}


async def execute(value: str) -> dict:
    """简单地返回输入的静态值。"""
    return {"output": value}
